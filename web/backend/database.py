"""Database engine, models, and session helpers.

The same models run on two backends:

* **Local development and tests** — SQLite, at ``DB_PATH`` (default ``reports.db``).
* **Azure** — Azure SQL Database, when ``AZURE_SQL_CONNECTION_STRING`` is set.

Production uses the Azure SQL *free offer*: a serverless database that
auto-pauses when idle. That drives three decisions in this module:

1. **No connection pooling** (``NullPool``). An idle pooled connection keeps a
   serverless database awake, which would burn the free monthly vCore
   allowance and then pause the database for the rest of the month.
2. **Passwordless auth.** Connections present a Microsoft Entra access token
   from the container's managed identity; no SQL password exists anywhere.
3. **Bounded retry while resuming.** The first connection after a pause fails
   with a transient error while the database wakes. Connecting retries those
   errors for a limited time, then raises ``DatabaseUnavailable`` (returned to
   clients as HTTP 503), so a request never outlives the 45-second limit of
   the Static Web Apps proxy in front of the API.
"""
from __future__ import annotations

import os
import re
import struct
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from observability import get_logger

log = get_logger(__name__)


def utcnow() -> datetime:
    """Current UTC time as a naive datetime; columns store UTC without a zone."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class DatabaseUnavailable(RuntimeError):
    """The database couldn't be reached within the retry budget (e.g. still resuming)."""


# Azure SQL error numbers that mean "try again shortly". 40613 is what a
# serverless database returns while it resumes from auto-pause.
TRANSIENT_SQL_ERRORS = {4221, 10928, 10929, 40197, 40501, 40613, 49918, 49919, 49920}
_ERROR_NUMBER = re.compile(r"\b(\d{4,5})\b")

# ODBC-level SQLSTATEs, not SQL Server error numbers: pyodbc reports these
# for its own client-side connection failures, which the regex above can't
# see (they're not a plain 4-5 digit number in the message). HYT00 is what
# the driver raises when its login attempt times out before a resuming
# (auto-paused) database finishes waking up — observed in production: a
# request landed mid-resume, this error skipped the retry loop entirely, and
# surfaced as a raw 500 instead of the designed 503 + Retry-After.
_TRANSIENT_ODBC_SQLSTATES = {"HYT00"}


def is_transient_error(exc: BaseException) -> bool:
    sqlstate = exc.args[0] if exc.args else None
    if isinstance(sqlstate, str) and sqlstate in _TRANSIENT_ODBC_SQLSTATES:
        return True
    message = " ".join(str(arg) for arg in exc.args) if exc.args else str(exc)
    return any(int(number) in TRANSIENT_SQL_ERRORS for number in _ERROR_NUMBER.findall(message))


def connect_with_retry(
    connect: Callable[[], object],
    *,
    budget_seconds: float = 25.0,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
):
    """Call ``connect`` until it succeeds, retrying only transient errors.

    Waits 2s, 4s, 8s… (capped at 10s) and never beyond ``budget_seconds`` in
    total, then raises ``DatabaseUnavailable``. Non-transient errors (bad
    credentials, firewall) are raised immediately — retrying won't fix them.
    The default budget plus one 10-second login attempt stays under 45 seconds.
    """
    deadline = clock() + budget_seconds
    delay = 2.0
    while True:
        try:
            return connect()
        except Exception as exc:
            if not is_transient_error(exc):
                raise
            remaining = deadline - clock()
            if remaining <= 0:
                raise DatabaseUnavailable("The database is starting up. Please retry shortly.") from exc
            wait = min(delay, remaining, 10.0)
            log.warning("Database not ready (%s); retrying in %.0fs", exc, wait)
            sleep(wait)
            delay *= 2


# pyodbc pre-connect attribute that carries a Microsoft Entra access token.
_SQL_COPT_SS_ACCESS_TOKEN = 1256
_AZURE_SQL_SCOPE = "https://database.windows.net/.default"


def _token_struct(token: str) -> bytes:
    """Encode a token the way the ODBC driver expects: UTF-16-LE bytes with a length prefix."""
    raw = token.encode("utf-16-le")
    return struct.pack(f"<I{len(raw)}s", len(raw), raw)


def _azure_sql_engine(odbc_connection_string: str) -> Engine:
    # Imported lazily so local development and CI (SQLite) don't need the
    # Microsoft ODBC driver installed.
    import pyodbc

    from azure_auth import get_credential

    credential = get_credential()

    def connect():
        # The token is passed as a connection attribute rather than using the
        # driver's own managed-identity mode, which is ambiguous about which
        # identity ID to supply outside App Service. Credentials cache tokens.
        token = credential.get_token(_AZURE_SQL_SCOPE).token
        return pyodbc.connect(
            odbc_connection_string,
            attrs_before={_SQL_COPT_SS_ACCESS_TOKEN: _token_struct(token)},
            timeout=10,
        )

    return create_engine(
        "mssql+pyodbc://",
        creator=lambda: connect_with_retry(connect),
        poolclass=NullPool,
    )


def build_engine() -> Engine:
    connection_string = os.getenv("AZURE_SQL_CONNECTION_STRING")
    if connection_string:
        return _azure_sql_engine(connection_string)
    db_path = os.getenv("DB_PATH", "reports.db")
    return create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})


engine = build_engine()
# expire_on_commit=False: objects stay readable after commit without another
# round trip — with no pool, every reload would open a fresh connection.
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Report(Base):
    __tablename__ = "reports"

    id             = Column(Integer, primary_key=True, index=True)
    type           = Column(String(20))   # "sheriff_sale" | "spot_check"
    created_at     = Column(DateTime, default=utcnow)
    title          = Column(String(300))
    property_count = Column(Integer, default=0)
    buy_count      = Column(Integer, default=0)
    consider_count = Column(Integer, default=0)
    no_buy_count   = Column(Integer, default=0)
    watch_count    = Column(Integer, default=0)
    perfect_count  = Column(Integer, default=0)
    avoid_count    = Column(Integer, default=0)
    pdf_path       = Column(String(500), nullable=True)
    deals_json     = Column(Text)         # JSON list of analyzed Deal dicts


class PropertyDeal(Base):
    __tablename__ = "property_deals"

    id           = Column(Integer, primary_key=True, index=True)
    sale_id      = Column(String(200), unique=True, index=True, nullable=False)
    source       = Column(String(20),  nullable=False)   # "sheriff_sale" | "spot_check"
    address      = Column(String(500), nullable=False)
    municipality = Column(String(200), nullable=True)
    deal_json    = Column(Text,        nullable=False)
    fingerprint  = Column(String(64),  nullable=True)    # SHA-256(address|min_bid|municipality)
    pdf_hash     = Column(String(64),  nullable=True)
    created_at   = Column(DateTime, default=utcnow)
    updated_at   = Column(DateTime, default=utcnow)


class Job(Base):
    """Progress of a background job, persisted so polling survives restarts."""
    __tablename__ = "jobs"

    id          = Column(String(36),  primary_key=True)        # UUID
    kind        = Column(String(30),  nullable=True)           # sheriff_sale | spot_check | share; rate limits count by kind
    status      = Column(String(20),  nullable=False)          # pending | running | done | error
    percent     = Column(Integer,     nullable=False, default=0)
    message     = Column(String(500), nullable=False, default="")
    report_id   = Column(Integer,     nullable=True)
    result_json = Column(Text,        nullable=True)           # job-specific result payload
    created_by  = Column(String(320), nullable=True)           # signed-in user, when known
    created_at  = Column(DateTime,    nullable=False, default=utcnow)
    updated_at  = Column(DateTime,    nullable=False, default=utcnow)


def run_migrations() -> None:
    """Apply all pending Alembic migrations (``alembic upgrade head``)."""
    from alembic import command
    from alembic.config import Config

    backend_dir = Path(__file__).resolve().parent
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "migrations"))
    command.upgrade(config, "head")


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
