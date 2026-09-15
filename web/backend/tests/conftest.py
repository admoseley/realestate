"""Shared pytest fixtures for the backend.

The app reads DB_PATH and REPORTS_DIR at *import* time (routers even create the
reports directory when imported), so the environment must point at a throwaway
location before anything imports ``main``. Otherwise tests would write a real
``reports.db`` and PDFs into the working tree.
"""
import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="realestate-tests-"))
os.environ.setdefault("DB_PATH", str(_TMP / "test.db"))
os.environ.setdefault("REPORTS_DIR", str(_TMP / "reports"))


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from main import app

    # Using TestClient as a context manager runs the app's startup hook, which
    # creates the database tables.
    with TestClient(app) as test_client:
        yield test_client
