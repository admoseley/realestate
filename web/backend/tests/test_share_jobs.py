"""Shares name deals by sale_id; the server loads them and emails in a background job."""
import uuid

import pytest

from database import SessionLocal
from deal_utils import upsert_deal

RECIPIENT = {"recipient_name": "Test Recipient", "recipient_email": "recipient@example.com"}


def stored_deal(**overrides) -> str:
    """Add a deal to the deal list and return its sale_id."""
    sale_id = f"test-{uuid.uuid4().hex[:8]}"
    deal = {"sale_id": sale_id, "address": f"{sale_id} Main St", "municipality": "Testville",
            "min_bid": 1000, "fmv": 50000, "verdict": "BUY", "score": 80, "red_flags": []}
    deal.update(overrides)
    with SessionLocal() as db:
        upsert_deal(db, sale_id=sale_id, source="sheriff_sale", address=deal["address"],
                    municipality=deal["municipality"], deal_dict=deal)
        db.commit()
    return sale_id


@pytest.fixture
def outbox(monkeypatch, fake_pdf):
    """Capture share emails instead of sending them."""
    monkeypatch.setenv("RESEND_API_KEY", "unused")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    sent = []

    def send(subject, html_body, recipient_name, recipient_email, pdf_path, pdf_name):
        sent.append({"subject": subject, "html": html_body, "to": recipient_email,
                     "pdf_name": pdf_name, "pdf": pdf_path.read_bytes()})

    monkeypatch.setattr("routers.share._send_via_resend", send)
    return sent


def start(client, path, body):
    response = client.post(path, json=body)
    job = client.get(f"/api/jobs/{response.json()['job_id']}").json() if response.is_success else None
    return response, job


def test_sharing_a_property_emails_the_stored_analysis(client, outbox):
    sale_id = stored_deal()

    response, job = start(client, "/api/share/property", {**RECIPIENT, "sale_id": sale_id})

    assert response.status_code == 200
    assert job["status"] == "done"
    assert job["result"] == {"recipient": "recipient@example.com", "count": 1}
    [email] = outbox
    assert email["to"] == "recipient@example.com"
    assert f"{sale_id} Main St" in email["subject"]
    assert email["pdf"].startswith(b"%PDF")


def test_deal_data_sent_by_the_client_is_ignored(client, outbox):
    sale_id = stored_deal()
    body = {**RECIPIENT, "sale_id": sale_id,
            "deal": {"address": "<a href='https://evil.example'>Injected</a>", "verdict": "BUY"}}

    start(client, "/api/share/property", body)

    [email] = outbox
    assert "Injected" not in email["html"]
    assert "Injected" not in email["subject"]


def test_sharing_an_unknown_deal_is_a_404_and_sends_nothing(client, outbox):
    response, _ = start(client, "/api/share/property", {**RECIPIENT, "sale_id": "no-such-deal"})

    assert response.status_code == 404
    assert "no-such-deal" in response.json()["detail"]
    assert outbox == []


def test_sharing_favorites_keeps_request_order_and_drops_repeats(client, outbox):
    first, second = stored_deal(), stored_deal()

    _, job = start(client, "/api/share/favorites",
                   {**RECIPIENT, "sale_ids": [second, first, second]})

    assert job["result"]["count"] == 2
    [email] = outbox
    assert email["html"].index(f"{second} Main St") < email["html"].index(f"{first} Main St")


def test_favorites_naming_a_missing_deal_are_rejected(client, outbox):
    response, _ = start(client, "/api/share/favorites",
                        {**RECIPIENT, "sale_ids": [stored_deal(), "gone"]})

    assert response.status_code == 404
    assert "gone" in response.json()["detail"]
    assert outbox == []


def test_favorites_need_at_least_one_deal(client, outbox):
    response, _ = start(client, "/api/share/favorites", {**RECIPIENT, "sale_ids": []})

    assert response.status_code == 422


def test_invalid_recipient_address_is_rejected(client, outbox):
    body = {**RECIPIENT, "recipient_email": "not-an-email", "sale_id": stored_deal()}

    response, _ = start(client, "/api/share/property", body)

    assert response.status_code == 400


def test_unconfigured_email_is_a_503_the_frontend_will_not_retry(client, monkeypatch, fake_pdf):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("SMTP_HOST", raising=False)

    response, _ = start(client, "/api/share/property", {**RECIPIENT, "sale_id": stored_deal()})

    assert response.status_code == 503
    assert "retry-after" not in response.headers


def test_a_delivery_failure_is_reported_on_the_job(client, monkeypatch, outbox):
    def provider_down(*_args):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr("routers.share._send_via_resend", provider_down)

    _, job = start(client, "/api/share/property", {**RECIPIENT, "sale_id": stored_deal()})

    assert job["status"] == "error"
    assert job["message"] == "Failed to send email: provider unavailable"
