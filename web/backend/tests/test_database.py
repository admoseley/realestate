"""Database helpers that make the serverless Azure SQL free offer workable."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

import database
from database import DatabaseUnavailable, connect_with_retry, is_transient_error

RESUMING = ("42000", "[Microsoft][ODBC Driver 18 for SQL Server][SQL Server]Database 'realestate' "
            "on server 'sql-realestate' is not currently available. Please retry the connection later. (40613)")


class FakeOdbcError(Exception):
    pass


class FakeClock:
    """Deterministic stand-in for time.monotonic/time.sleep."""

    def __init__(self):
        self.now = 0.0

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def test_resume_error_is_transient_but_login_failure_is_not():
    assert is_transient_error(FakeOdbcError(*RESUMING))
    assert not is_transient_error(FakeOdbcError("28000", "Login failed for user '<token-identified principal>'. (18456)"))


def test_retry_succeeds_once_the_database_resumes():
    time = FakeClock()
    attempts = []

    def connect():
        attempts.append(time.now)
        if len(attempts) < 3:
            raise FakeOdbcError(*RESUMING)
        return "connection"

    assert connect_with_retry(connect, sleep=time.sleep, clock=time.clock) == "connection"
    assert len(attempts) == 3


def test_retry_gives_up_within_the_budget():
    time = FakeClock()

    def connect():
        raise FakeOdbcError(*RESUMING)

    with pytest.raises(DatabaseUnavailable):
        connect_with_retry(connect, budget_seconds=25, sleep=time.sleep, clock=time.clock)
    assert time.now <= 25


def test_non_transient_errors_are_raised_without_retrying():
    calls = []

    def connect():
        calls.append(1)
        raise FakeOdbcError("28000", "Login failed (18456)")

    with pytest.raises(FakeOdbcError):
        connect_with_retry(connect, sleep=lambda _: None)
    assert len(calls) == 1


def test_engine_does_not_wrap_database_unavailable():
    # The API's 503 handler matches on DatabaseUnavailable, so SQLAlchemy must
    # pass it through unchanged when the connection creator raises it.
    def creator():
        raise DatabaseUnavailable("resuming")

    engine = create_engine("sqlite://", creator=creator, poolclass=NullPool)
    with pytest.raises(DatabaseUnavailable):
        engine.connect()


def test_access_token_is_length_prefixed_utf16():
    encoded = database._token_struct("abc")

    assert encoded[:4] == (6).to_bytes(4, "little")
    assert encoded[4:] == "abc".encode("utf-16-le")
