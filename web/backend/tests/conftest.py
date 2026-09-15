"""Shared pytest fixtures for the backend.

The app reads its configuration at *import* time (database location, reports
directory — routers even create that directory when imported), so the
environment must point at a throwaway location before anything imports the
app. Otherwise tests would write a real ``reports.db`` and PDFs into the
working tree, or — if Azure settings were exported in the shell — try to
reach a real Azure SQL database.
"""
import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="realestate-tests-"))
os.environ["DB_PATH"] = str(_TMP / "test.db")
os.environ["REPORTS_DIR"] = str(_TMP / "reports")
os.environ.pop("AZURE_SQL_CONNECTION_STRING", None)
os.environ.pop("REPORTS_BLOB_URL", None)


@pytest.fixture(scope="session")
def migrated_db():
    """Apply the Alembic migrations to the test database once per session."""
    from database import run_migrations

    run_migrations()


@pytest.fixture(scope="session")
def client(migrated_db):
    from fastapi.testclient import TestClient

    from main import app

    # Using TestClient as a context manager runs the app's lifespan (migrations
    # and orphaned-job cleanup), just like production startup.
    with TestClient(app) as test_client:
        yield test_client
