"""Storage for generated report PDFs.

Report PDFs used to be written to the container's local disk, which is wiped
whenever the container restarts or redeploys, leaving reports that pointed at
files that no longer existed. PDFs now live in:

* **Azure Blob Storage** when ``REPORTS_BLOB_URL`` is set (the container URL,
  e.g. ``https://<account>.blob.core.windows.net/reports``), authenticated with
  the managed identity — no storage account keys.
* **A local directory** otherwise (``REPORTS_DIR``, default
  ``web/backend/reports``) for development and tests.

A report stores only its PDF's *name* as the storage key. Keys are reduced to
a bare file name before use: that accepts older rows holding absolute paths,
and stops a crafted key from reaching outside the local reports directory.
"""
from __future__ import annotations

import os
import shutil
from functools import lru_cache
from pathlib import Path
from typing import Iterator, Protocol

from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import ContainerClient, ContentSettings

PDF_CONTENT_TYPE = "application/pdf"
_CHUNK_SIZE = 1024 * 1024


class ReportNotFound(FileNotFoundError):
    """The requested report PDF isn't in storage."""


def key_for(path_or_key: str) -> str:
    """Normalize a stored value (key or legacy absolute path) to a bare file name."""
    name = Path(path_or_key).name
    if name in ("", ".", ".."):
        raise ReportNotFound(path_or_key)
    return name


class ReportStorage(Protocol):
    def save_pdf(self, local_file: Path) -> str: ...
    def exists(self, key: str) -> bool: ...
    def stream(self, key: str) -> Iterator[bytes]: ...
    def delete(self, key: str) -> None: ...


class LocalReportStorage:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.root / key_for(key)

    def save_pdf(self, local_file: Path) -> str:
        key = key_for(local_file.name)
        shutil.copyfile(local_file, self.root / key)
        return key

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def stream(self, key: str) -> Iterator[bytes]:
        path = self._path(key)
        if not path.is_file():
            raise ReportNotFound(key)
        # Open now, so a missing file surfaces as ReportNotFound here rather
        # than as an error halfway through a streaming response.
        handle = path.open("rb")

        def chunks() -> Iterator[bytes]:
            with handle:
                while chunk := handle.read(_CHUNK_SIZE):
                    yield chunk

        return chunks()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class BlobReportStorage:
    def __init__(self, container: ContainerClient):
        self.container = container

    def save_pdf(self, local_file: Path) -> str:
        key = key_for(local_file.name)
        with local_file.open("rb") as data:
            self.container.upload_blob(
                key,
                data,
                overwrite=True,
                content_settings=ContentSettings(content_type=PDF_CONTENT_TYPE),
            )
        return key

    def exists(self, key: str) -> bool:
        return self.container.get_blob_client(key_for(key)).exists()

    def stream(self, key: str) -> Iterator[bytes]:
        try:
            downloader = self.container.download_blob(key_for(key))
        except ResourceNotFoundError as exc:
            raise ReportNotFound(key) from exc
        return downloader.chunks()

    def delete(self, key: str) -> None:
        try:
            self.container.delete_blob(key_for(key))
        except ResourceNotFoundError:
            pass


def build_storage() -> ReportStorage:
    blob_url = os.getenv("REPORTS_BLOB_URL")
    if blob_url:
        from azure_auth import get_credential

        return BlobReportStorage(ContainerClient.from_container_url(blob_url, credential=get_credential()))
    default_dir = Path(__file__).resolve().parent / "reports"
    return LocalReportStorage(Path(os.getenv("REPORTS_DIR", str(default_dir))))


@lru_cache(maxsize=1)
def get_storage() -> ReportStorage:
    return build_storage()
