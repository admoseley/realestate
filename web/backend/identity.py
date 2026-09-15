"""Who is making a request, as far as the API can tell.

Static Web Apps signs users in at the edge and adds an ``x-ms-client-principal``
header to the requests it proxies: Base64-encoded JSON with ``identityProvider``,
``userId``, ``userDetails`` (email or username), and ``userRoles``.

Microsoft documents that header for managed Functions backends; for a linked
Container Apps backend it's best-effort. Access control therefore lives in the
edge routes (``staticwebapp.config.json``), never here. This identity is used
only to attribute work (``jobs.created_by``) and to key per-user rate limits,
which are backed by an app-wide limit that holds even without it.
"""
import base64
import binascii
import json
from typing import Optional

from fastapi import Request

PRINCIPAL_HEADER = "x-ms-client-principal"
MAX_USER_LENGTH = 320   # size of jobs.created_by


def client_principal(request: Request) -> Optional[dict]:
    """The decoded client principal, or None if the header is absent or malformed."""
    header = request.headers.get(PRINCIPAL_HEADER)
    if not header:
        return None
    try:
        principal = json.loads(base64.b64decode(header, validate=True))
    except (binascii.Error, ValueError):   # bad Base64, bad UTF-8, or bad JSON
        return None
    return principal if isinstance(principal, dict) else None


def current_user(request: Request) -> Optional[str]:
    """FastAPI dependency: the signed-in user's email or username (or their
    Static Web Apps user ID), or None when the request carries no principal."""
    principal = client_principal(request)
    if not principal:
        return None
    user = principal.get("userDetails") or principal.get("userId")
    return str(user)[:MAX_USER_LENGTH] if user else None
