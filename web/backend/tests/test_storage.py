"""Report PDF storage: a local directory in development, Azure Blob Storage in Azure."""
import pytest
from azure.core.exceptions import ResourceNotFoundError

import azure_auth
import storage
from storage import BlobReportStorage, LocalReportStorage, ReportNotFound

PDF = b"%PDF-1.4 fake report"
NAME = "SheriffSale_1_09152026-120000.pdf"


class FakeDownloader:
    def __init__(self, data):
        self.data = data

    def chunks(self):
        yield self.data[:4]
        yield self.data[4:]


class FakeBlobClient:
    def __init__(self, blobs, name):
        self.blobs = blobs
        self.name = name

    def exists(self):
        return self.name in self.blobs


class FakeContainerClient:
    """The subset of azure.storage.blob.ContainerClient that storage.py uses."""

    def __init__(self):
        self.blobs = {}
        self.content_types = {}

    def upload_blob(self, name, data, overwrite=False, content_settings=None):
        self.blobs[name] = data.read()
        self.content_types[name] = content_settings.content_type

    def get_blob_client(self, name):
        return FakeBlobClient(self.blobs, name)

    def download_blob(self, name):
        if name not in self.blobs:
            raise ResourceNotFoundError("The specified blob does not exist.")
        return FakeDownloader(self.blobs[name])

    def delete_blob(self, name):
        if name not in self.blobs:
            raise ResourceNotFoundError("The specified blob does not exist.")
        del self.blobs[name]


def make_pdf(directory, name=NAME):
    path = directory / name
    path.write_bytes(PDF)
    return path


@pytest.fixture(params=["local", "blob"])
def backend(request, tmp_path):
    if request.param == "local":
        return LocalReportStorage(tmp_path / "reports")
    return BlobReportStorage(FakeContainerClient())


def test_save_stream_and_delete_round_trip(backend, tmp_path):
    key = backend.save_pdf(make_pdf(tmp_path))

    assert key == NAME
    assert backend.exists(key)
    assert b"".join(backend.stream(key)) == PDF

    backend.delete(key)
    assert not backend.exists(key)


def test_streaming_a_missing_pdf_raises_report_not_found(backend):
    with pytest.raises(ReportNotFound):
        backend.stream("missing.pdf")


def test_deleting_a_missing_pdf_is_a_no_op(backend):
    backend.delete("missing.pdf")


def test_legacy_absolute_paths_resolve_to_their_file_name(backend, tmp_path):
    key = backend.save_pdf(make_pdf(tmp_path))

    assert backend.exists(f"/app/web/backend/reports/{key}")


def test_local_keys_cannot_escape_the_reports_directory(tmp_path):
    local = LocalReportStorage(tmp_path / "reports")
    (tmp_path / "secret.pdf").write_bytes(b"not a report")

    with pytest.raises(ReportNotFound):
        local.stream("../secret.pdf")


def test_blob_uploads_are_tagged_as_pdf(tmp_path):
    container = FakeContainerClient()
    key = BlobReportStorage(container).save_pdf(make_pdf(tmp_path))

    assert container.content_types[key] == "application/pdf"


def test_blob_storage_is_used_when_a_container_url_is_configured(monkeypatch):
    monkeypatch.setenv("REPORTS_BLOB_URL", "https://example.blob.core.windows.net/reports")
    monkeypatch.setenv("AZURE_CLIENT_ID", "00000000-0000-0000-0000-000000000000")
    azure_auth.get_credential.cache_clear()
    try:
        selected = storage.build_storage()

        assert isinstance(selected, BlobReportStorage)
        assert selected.container.container_name == "reports"
    finally:
        azure_auth.get_credential.cache_clear()


def test_local_storage_is_the_default(monkeypatch, tmp_path):
    monkeypatch.delenv("REPORTS_BLOB_URL", raising=False)
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path / "local"))

    assert isinstance(storage.build_storage(), LocalReportStorage)
