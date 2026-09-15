"""Sheriff-sale uploads must not share temporary files.

Every upload used to extract text to the same /tmp file, and ``pdf_to_text``
reuses an existing output file — so two concurrent uploads could analyze the
wrong PDF. Each job now gets its own directory, removed when the job ends.
"""
import routers.sheriff_sale as sheriff_sale


def test_each_upload_gets_its_own_workdir_which_is_cleaned_up(client, monkeypatch):
    text_paths = []

    def fake_pdf_to_text(pdf_path, txt_path):
        text_paths.append(txt_path)
        txt_path.write_text("")
        return txt_path

    monkeypatch.setattr(sheriff_sale, "pdf_to_text", fake_pdf_to_text)
    # No properties parsed: the job ends cleanly with an error status.
    monkeypatch.setattr(sheriff_sale, "parse_sheriff_text", lambda _path: [])

    for _ in range(2):
        response = client.post(
            "/api/sheriff-sale/upload",
            data={"enrich": "false"},
            files={"file": ("sale.pdf", b"%PDF-1.4 test", "application/pdf")},
        )
        assert response.status_code == 200
        job = client.get(f"/api/jobs/{response.json()['job_id']}").json()
        assert job["status"] == "error"
        assert "No properties" in job["message"]

    first, second = (path.parent for path in text_paths)
    assert first != second
    assert not first.exists()
    assert not second.exists()


def test_non_pdf_uploads_are_rejected(client):
    response = client.post(
        "/api/sheriff-sale/upload",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 400
