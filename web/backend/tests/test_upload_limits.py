"""Upload validation, and the debug report's off switch."""
import routers.sheriff_sale as sheriff_sale
import uploads


def upload(client, path, content, name="sale.pdf"):
    return client.post(path, data={"enrich": "false"},
                       files={"file": (name, content, "application/pdf")})


def no_properties(monkeypatch):
    """Let an accepted upload's background job end quickly, without poppler."""
    def fake_pdf_to_text(_pdf_path, txt_path):
        txt_path.write_text("")
        return txt_path

    monkeypatch.setattr(sheriff_sale, "pdf_to_text", fake_pdf_to_text)
    monkeypatch.setattr(sheriff_sale, "parse_sheriff_text", lambda _path: [])


def test_pdfs_over_the_size_limit_are_rejected(client, monkeypatch):
    monkeypatch.setattr(uploads, "MAX_UPLOAD_BYTES", 64)

    response = upload(client, "/api/sheriff-sale/upload", b"%PDF-1.4 " + b"x" * 100)

    assert response.status_code == 413


def test_files_named_pdf_must_actually_be_pdfs(client):
    response = upload(client, "/api/sheriff-sale/upload", b"MZ\x90\x00 an executable, not a PDF")

    assert response.status_code == 400
    assert "not a valid PDF" in response.json()["detail"]


def test_a_pdf_header_after_a_few_leading_bytes_is_accepted(client, monkeypatch):
    no_properties(monkeypatch)

    response = upload(client, "/api/sheriff-sale/upload", b"\r\n\r\n%PDF-1.7 body")

    assert response.status_code == 200


def test_debug_reports_are_off_by_default(client):
    response = upload(client, "/api/debug/analyze-pdf", b"%PDF-1.4 test")

    assert response.status_code == 404


def test_debug_reports_work_when_enabled(client, monkeypatch):
    monkeypatch.setenv("ENABLE_DEBUG", "true")
    monkeypatch.setattr("routers.debug._build_report",
                        lambda filename, _content, _workdir: f"report for {filename}")

    response = upload(client, "/api/debug/analyze-pdf", b"%PDF-1.4 test")

    assert response.status_code == 200
    assert response.text == "report for sale.pdf"


def test_debug_uploads_are_validated_too(client, monkeypatch):
    monkeypatch.setenv("ENABLE_DEBUG", "true")

    response = upload(client, "/api/debug/analyze-pdf", b"plain text")

    assert response.status_code == 400
