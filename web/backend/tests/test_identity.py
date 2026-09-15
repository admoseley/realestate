"""Reading the signed-in user from the header Static Web Apps adds."""
import base64
import json

import pytest
from starlette.requests import Request

from identity import client_principal, current_user


def request_with(headers: dict) -> Request:
    raw = [(name.lower().encode(), value.encode()) for name, value in headers.items()]
    return Request({"type": "http", "headers": raw})


def encoded(value) -> str:
    return base64.b64encode(json.dumps(value).encode()).decode()


def test_the_signed_in_user_is_read_from_the_principal():
    principal = {"identityProvider": "aad", "userId": "abc123",
                 "userDetails": "analyst@example.com", "userRoles": ["authenticated", "analyst"]}
    request = request_with({"x-ms-client-principal": encoded(principal)})

    assert client_principal(request)["userRoles"] == ["authenticated", "analyst"]
    assert current_user(request) == "analyst@example.com"


def test_the_user_id_stands_in_when_there_are_no_user_details():
    request = request_with({"x-ms-client-principal": encoded({"userId": "abc123"})})

    assert current_user(request) == "abc123"


def test_requests_without_a_principal_are_anonymous():
    assert current_user(request_with({})) is None


@pytest.mark.parametrize("header", [
    "not base64!",
    base64.b64encode(b"not json").decode(),
    base64.b64encode(b"\xff\xfe\xfa").decode(),
    encoded(["a", "list"]),
])
def test_malformed_principals_are_ignored(header):
    assert current_user(request_with({"x-ms-client-principal": header})) is None


def test_user_names_are_capped_to_the_column_size():
    request = request_with({"x-ms-client-principal": encoded({"userDetails": "x" * 1000})})

    assert len(current_user(request)) == 320
