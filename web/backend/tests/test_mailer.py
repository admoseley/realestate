"""All outbound email goes through mailer.py."""
import mailer


def test_email_is_configured_only_with_a_resend_key(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    assert not mailer.is_configured()

    monkeypatch.setenv("RESEND_API_KEY", "unused")
    assert mailer.is_configured()


def test_display_names_cannot_smuggle_in_recipients_or_headers():
    address = mailer.format_address('Eve <eve@evil.example>, "Mallory";\r\nBcc: x', "recipient@example.com")

    assert address.endswith(" <recipient@example.com>")
    assert address.count("<") == 1
    assert not any(char in address[: -len(" <recipient@example.com>")] for char in ',;:"\r\n<>')


def test_a_display_name_with_nothing_left_sends_to_the_bare_address():
    assert mailer.format_address(' <> ', "recipient@example.com") == "recipient@example.com"


def test_send_email_builds_the_resend_request(monkeypatch, tmp_path):
    monkeypatch.setenv("RESEND_API_KEY", "unused")
    monkeypatch.setenv("FROM_EMAIL", "reports@example.com")
    monkeypatch.setenv("FROM_NAME", "Example Reports")
    sent = []
    monkeypatch.setattr(mailer.resend.Emails, "send", lambda params: sent.append(params))
    pdf = tmp_path / "Report.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    mailer.send_email(to_name="Jane Smith", to_email="jane@example.com",
                      subject="Property Analysis\r\nBcc: x", html="<p>hi</p>", attachment=pdf)

    [params] = sent
    assert params["from"] == "Example Reports <reports@example.com>"
    assert params["to"] == ["Jane Smith <jane@example.com>"]
    assert params["subject"] == "Property Analysis Bcc: x"
    assert params["attachments"] == [{"filename": "Report.pdf", "content": list(b"%PDF-1.4")}]
