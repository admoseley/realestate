"""Report PDFs are served from, and removed from, report storage."""
import uuid

from database import Report, SessionLocal
from storage import get_storage

PDF = b"%PDF-1.4 stored report"


def create_report_with_pdf(tmp_path):
    pdf = tmp_path / f"SpotCheck_{uuid.uuid4().hex}.pdf"
    pdf.write_bytes(PDF)
    key = get_storage().save_pdf(pdf)
    with SessionLocal() as db:
        report = Report(type="spot_check", title="123 TEST ST", property_count=1,
                        pdf_path=key, deals_json="[]")
        db.add(report)
        db.commit()
        return report.id, key


def test_pdf_download_streams_from_storage(client, tmp_path):
    report_id, key = create_report_with_pdf(tmp_path)

    response = client.get(f"/api/reports/{report_id}/pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert key in response.headers["content-disposition"]
    assert response.content == PDF


def test_listing_reports_does_not_query_storage(client, tmp_path, monkeypatch):
    report_id, _ = create_report_with_pdf(tmp_path)

    def fail():
        raise AssertionError("listing reports should not touch storage")

    monkeypatch.setattr("routers.reports.get_storage", fail)
    reports = {r["id"]: r for r in client.get("/api/reports").json()}

    assert reports[report_id]["has_pdf"] is True


def test_deleting_a_report_removes_its_pdf(client, tmp_path):
    report_id, key = create_report_with_pdf(tmp_path)

    assert client.delete(f"/api/reports/{report_id}").status_code == 204
    assert not get_storage().exists(key)
    assert client.get(f"/api/reports/{report_id}/pdf").status_code == 404


def test_a_pdf_missing_from_storage_returns_404(client, tmp_path):
    report_id, key = create_report_with_pdf(tmp_path)
    get_storage().delete(key)

    assert client.get(f"/api/reports/{report_id}/pdf").status_code == 404
