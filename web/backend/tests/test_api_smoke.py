"""Smoke tests for the FastAPI app: it boots, routes are wired, and a fresh
database behaves as expected."""


def test_core_routes_are_registered(client):
    paths = client.get("/openapi.json").json()["paths"]

    for path in (
        "/api/reports",
        "/api/deals",
        "/api/jobs/{job_id}",
        "/api/sheriff-sale/upload",
        "/api/spot-check",
        "/api/share/property",
    ):
        assert path in paths


def test_reports_are_empty_on_a_fresh_database(client):
    response = client.get("/api/reports")

    assert response.status_code == 200
    assert response.json() == []


def test_unknown_job_returns_404(client):
    assert client.get("/api/jobs/does-not-exist").status_code == 404


def test_health_does_not_need_the_database(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_database_health_reports_ready(client):
    response = client.get("/api/health/db")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_database_unavailable_becomes_503_with_retry_after(client, monkeypatch):
    from database import DatabaseUnavailable

    def unavailable(_job_id):
        raise DatabaseUnavailable("The database is starting up. Please retry shortly.")

    monkeypatch.setattr("main.get_job", unavailable)
    response = client.get("/api/jobs/any")

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "10"
