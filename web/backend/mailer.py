"""Outbound email.

The only module that talks to an email provider. It uses Resend today; moving
to Azure Communication Services (issue #11) should mean changing only this
file. The old SMTP fallback is gone: it was unused, and it built message
headers straight from user input.
"""
import os
import re
from pathlib import Path
from typing import Optional

import resend

DEFAULT_FROM_EMAIL = "contact@estellawilson.com"
DEFAULT_FROM_NAME  = "Estella Wilson Properties LLC"

# Characters that could end a display name early, add recipients, or start a
# new header line.
_UNSAFE_DISPLAY_CHARS = re.compile(r'[\x00-\x1f\x7f"<>,;:\\]')


def is_configured() -> bool:
    """Whether email can be sent. In Azure the key reaches the container as an
    environment variable from a Key Vault secret reference."""
    return bool(os.getenv("RESEND_API_KEY"))


def format_address(name: str, email: str) -> str:
    """``Name <email>`` with a display name that can't smuggle in extra
    recipients or headers. Falls back to the bare address when nothing is left."""
    safe_name = " ".join(_UNSAFE_DISPLAY_CHARS.sub(" ", name or "").split())
    return f"{safe_name} <{email}>" if safe_name else email


def send_email(*, to_name: str, to_email: str, subject: str, html: str,
               attachment: Path, attachment_name: Optional[str] = None) -> None:
    """Send one HTML email with a PDF attachment. Raises if the provider refuses it."""
    resend.api_key = os.getenv("RESEND_API_KEY")
    sender = format_address(os.getenv("FROM_NAME", DEFAULT_FROM_NAME),
                            os.getenv("FROM_EMAIL", DEFAULT_FROM_EMAIL))
    params: resend.Emails.SendParams = {
        "from":        sender,
        "to":          [format_address(to_name, to_email)],
        "subject":     " ".join(subject.split()),   # a header: no line breaks
        "html":        html,
        "attachments": [{"filename": attachment_name or attachment.name,
                         "content":  list(attachment.read_bytes())}],
    }
    resend.Emails.send(params)
