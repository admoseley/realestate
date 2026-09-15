"""Shares name deals by sale_id; the server loads them and emails in a background job."""
import base64
import json
import uuid
from datetime import timedelta

import pytest

import jobs
from database import Job, SessionLocal, utcnow
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
    sent = []

    def send(*, to_name, to_email, subject, html, attachment, attachment_name=None):
        sent.append({"subject": subject, "html": html, "to": to_email,
                     "pdf_name": attachment_name, "pdf": attachment.read_bytes()})

    monkeypatch.setattr("mailer.send_email", send)
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

    response, _ = start(client, "/api/share/property", {**RECIPIENT, "sale_id": stored_deal()})

    assert response.status_code == 503
    assert "retry-after" not in response.headers


def test_a_delivery_failure_is_reported_on_the_job(client, monkeypatch, outbox):
    def provider_down(**_email):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr("mailer.send_email", provider_down)

    _, job = start(client, "/api/share/property", {**RECIPIENT, "sale_id": stored_deal()})

    assert job["status"] == "error"
    assert job["message"] == "Failed to send email: provider unavailable"


# ── Hardening (#5) ───────────────────────────────────────────────────────────

def principal_header(user: str) -> dict:
    """The header Static Web Apps adds to requests from a signed-in user."""
    principal = {"identityProvider": "aad", "userId": uuid.uuid4().hex,
                 "userDetails": user, "userRoles": ["anonymous", "authenticated", "analyst"]}
    return {"x-ms-client-principal": base64.b64encode(json.dumps(principal).encode()).decode()}


def unique_user() -> str:
    return f"{uuid.uuid4().hex[:8]}@example.com"


def test_text_typed_by_the_user_is_escaped_in_the_email(client, outbox):
    body = {"recipient_name": "<script>alert(1)</script>", "recipient_email": "recipient@example.com",
            "sender_name": "<i>Eve</i>", "note": "<b>Look</b>\nat this", "sale_id": stored_deal()}

    start(client, "/api/share/property", body)

    [email] = outbox
    assert "<script>" not in email["html"]
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in email["html"]
    assert "&lt;i&gt;Eve&lt;/i&gt;" in email["html"]
    assert "&lt;b&gt;Look&lt;/b&gt;<br>at this" in email["html"]


@pytest.mark.parametrize("endpoint", ["property", "favorites"])
def test_stored_deal_text_is_escaped_too(client, outbox, endpoint):
    sale_id = stored_deal(red_flags=["<img src=x onerror=alert(1)>"],
                          recommendation="<a href='https://evil.example'>go</a>")
    body = {**RECIPIENT, "sale_id": sale_id} if endpoint == "property" else {**RECIPIENT, "sale_ids": [sale_id]}

    start(client, f"/api/share/{endpoint}", body)

    [email] = outbox
    assert "<img" not in email["html"]
    assert "&lt;img src=x onerror=alert(1)&gt;" in email["html"]
    assert "evil.example&#x27;&gt;go&lt;/a&gt;" in email["html"]


def test_overlong_notes_are_rejected(client, outbox):
    response = client.post("/api/share/property",
                           json={**RECIPIENT, "note": "x" * 2001, "sale_id": stored_deal()})

    assert response.status_code == 422
    assert outbox == []


def test_shares_record_their_kind_and_who_sent_them(client, outbox):
    user = unique_user()

    response = client.post("/api/share/property", json={**RECIPIENT, "sale_id": stored_deal()},
                           headers=principal_header(user))

    with SessionLocal() as db:
        job = db.get(Job, response.json()["job_id"])
        assert (job.kind, job.created_by) == ("share", user)


def test_each_user_has_an_hourly_share_limit(client, outbox, monkeypatch):
    monkeypatch.setenv("SHARE_LIMIT_PER_USER_PER_HOUR", "2")
    body = {**RECIPIENT, "sale_id": stored_deal()}
    heavy_sharer = principal_header(unique_user())

    statuses = [client.post("/api/share/property", json=body, headers=heavy_sharer).status_code
                for _ in range(3)]

    assert statuses == [200, 200, 429]
    assert client.post("/api/share/property", json=body,
                       headers=principal_header(unique_user())).status_code == 200


def test_the_app_has_an_overall_hourly_share_limit(client, outbox, monkeypatch):
    shares_this_hour = jobs.count_jobs_since("share", utcnow() - timedelta(hours=1))
    monkeypatch.setenv("SHARE_LIMIT_PER_HOUR", str(shares_this_hour + 1))
    body = {**RECIPIENT, "sale_id": stored_deal()}

    assert client.post("/api/share/property", json=body).status_code == 200
    limited = client.post("/api/share/property", json=body)

    assert limited.status_code == 429
    assert "retry-after" not in limited.headers   # so the frontend won't retry it
    assert len(outbox) == 1
