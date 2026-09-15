"""Spot checks run as background jobs; the finished job carries the analysis."""
import uuid

import pytest

from deal_utils import spot_sale_id


@pytest.fixture(autouse=True)
def offline(monkeypatch, fake_pdf):
    """No geocoding or PDF map downloads; lookups are skipped via no_lookup."""
    monkeypatch.setattr("routers.spot_check.geocode_nominatim", lambda _address: None)


def spot_check_request(**overrides):
    request = {
        "address": f"{uuid.uuid4().hex[:6]} Test St, Pittsburgh, PA 15212",
        "price": 50000,
        "no_lookup": True,
    }
    request.update(overrides)
    return request


def run(client, request):
    started = client.post("/api/spot-check", json=request)
    assert started.status_code == 200
    # TestClient runs background tasks before returning, so the job is finished.
    return client.get(f"/api/jobs/{started.json()['job_id']}").json()


def test_spot_check_returns_a_job_that_finishes_with_the_analysis(client):
    request = spot_check_request(fmv=90000)

    job = run(client, request)

    assert job["status"] == "done"
    assert job["result"]["deal"]["address"] == request["address"]
    assert job["result"]["deal"]["verdict"]
    assert job["result"]["warning"] is None
    assert client.get(f"/api/reports/{job['report_id']}/pdf").status_code == 200


def test_missing_fmv_falls_back_to_price_with_a_warning(client):
    job = run(client, spot_check_request())

    assert job["result"]["deal"]["fmv"] == 50000
    assert "no assessed value" in job["result"]["warning"]


def test_spot_check_adds_the_property_to_the_deal_list(client):
    request = spot_check_request()

    run(client, request)

    sale_ids = {deal["sale_id"] for deal in client.get("/api/deals").json()}
    assert spot_sale_id(request["address"], request["price"]) in sale_ids


@pytest.mark.parametrize("overrides", [{"address": "x" * 301}, {"address": ""}, {"price": 0}])
def test_invalid_spot_check_requests_are_rejected(client, overrides):
    assert client.post("/api/spot-check", json=spot_check_request(**overrides)).status_code == 422


def test_a_failing_spot_check_reports_the_error_on_the_job(client, monkeypatch):
    def broken(_deal):
        raise RuntimeError("analyzer exploded")

    monkeypatch.setattr("routers.spot_check.analyze", broken)

    job = run(client, spot_check_request())

    assert job["status"] == "error"
    assert job["message"] == "Spot check failed: analyzer exploded"
