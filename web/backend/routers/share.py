import logging
import os
import re
import sys
import smtplib
import tempfile
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

import resend
from fastapi import APIRouter, BackgroundTasks, HTTPException

sys.path.insert(0, str(Path(__file__).parents[3]))

from investment_analyzer import Deal
from generate_pdf_report import build_and_save_pdf

from database import SessionLocal, utcnow
from deal_utils import deal_records_by_sale_id
from jobs import JobError, complete_job, create_job, run_job, update_job
from models import JobStarted, ShareRequest, SharePropertyRequest, ShareFavoritesRequest

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/share", tags=["share"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

FROM_EMAIL = os.getenv("FROM_EMAIL", "contact@estellawilson.com")
FROM_NAME  = os.getenv("FROM_NAME",  "Estella Wilson Properties LLC")


def _build_html(deal: dict, sender_name: str, recipient_name: str, **kwargs) -> str:
    fmt  = lambda v: f"${v:,.0f}" if v is not None else "—"
    fmtp = lambda v: f"{v:.1f}%" if v is not None else "—"

    verdict = deal.get("verdict", "")
    verdict_color = {"BUY": "#27AE60", "CONSIDER": "#F5A51B",
                     "NO BUY": "#E74C3C", "WATCH": "#F39C12"}.get(verdict, "#666666")

    red_flags_html = "".join(
        f"<li style='color:#E74C3C;margin-bottom:4px;'>&#9888; {f}</li>"
        for f in (deal.get("red_flags") or [])
    )
    red_flags_block = (
        f"<ul style='margin:0;padding-left:20px;'>{red_flags_html}</ul>"
        if red_flags_html
        else "<p style='color:#27AE60;margin:0;'>None identified</p>"
    )

    recommendation = deal.get("recommendation") or deal.get("strategy") or ""
    recommendation_block = ""
    if recommendation:
        recommendation_block = f"""
        <tr>
          <td style="padding:0 28px 16px 28px;border-top:1px solid #DDDDDD;">
            <p style="margin:12px 0 6px 0;font-size:12px;font-weight:bold;color:#2B2B2B;
                      text-transform:uppercase;letter-spacing:0.5px;">Recommendation</p>
            <p style="margin:0;font-size:13px;color:#2B2B2B;line-height:1.5;">{recommendation}</p>
          </td>
        </tr>"""

    sender_line = (
        f"<p style='margin:0 0 4px 0;'>{sender_name} has shared a property analysis with you.</p>"
        if sender_name
        else "<p style='margin:0 0 4px 0;'>A property analysis has been shared with you.</p>"
    )

    note = kwargs.get("note", "")
    note_block = ""
    if note:
        note_block = f"""
        <tr>
          <td style="padding:0 28px 16px 28px;border-top:1px solid #DDDDDD;">
            <p style="margin:12px 0 6px 0;font-size:12px;font-weight:bold;color:#2B2B2B;
                      text-transform:uppercase;letter-spacing:0.5px;">Note from Sender</p>
            <p style="margin:0;font-size:13px;color:#2B2B2B;line-height:1.6;
                      background:#F9F9F9;border-left:3px solid #F5A51B;padding:10px 14px;
                      border-radius:0 6px 6px 0;">{note}</p>
          </td>
        </tr>"""

    sqft_str   = f" &middot; {int(deal['sqft']):,} sqft" if deal.get("sqft") else ""
    built_str  = f" &middot; Built {deal['year_built']}" if deal.get("year_built") else ""
    case_str   = f" &middot; Case {deal['case']}" if deal.get("case") else ""
    rating_str = (f" &nbsp;<span style='font-size:12px;color:#666666;font-weight:bold;'>"
                  f"{deal['perfect_pass_rating']}</span>"
                  if deal.get("perfect_pass_rating") else "")

    flip_color = "#27AE60" if (deal.get("flip_net_profit") or 0) > 0 else "#E74C3C"
    dscr_str   = f"{deal['dscr']:.2f}" if deal.get("dscr") is not None else "—"

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#F4F4F4;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#F4F4F4;padding:24px 0;">
  <tr><td align="center">
    <table width="600" cellpadding="0" cellspacing="0"
           style="background:#ffffff;border-radius:8px;overflow:hidden;border:1px solid #DDDDDD;">

      <tr>
        <td style="background:#F5A51B;padding:20px 28px;">
          <p style="margin:0;color:#ffffff;font-size:11px;font-weight:bold;
                    letter-spacing:1px;text-transform:uppercase;">
            Estella Wilson Properties LLC
          </p>
          <p style="margin:4px 0 0 0;color:#ffffff;font-size:20px;font-weight:bold;">
            Property Investment Analysis
          </p>
        </td>
      </tr>

      <tr>
        <td style="padding:20px 28px 8px 28px;color:#2B2B2B;font-size:14px;
                   border-bottom:1px solid #DDDDDD;">
          <p style="margin:0 0 4px 0;">Hello {recipient_name},</p>
          {sender_line}
          <p style="margin:8px 0 0 0;color:#666666;font-size:12px;">
            The full analysis is attached as a PDF. Key metrics are summarized below.
          </p>
        </td>
      </tr>

      <tr>
        <td style="background:#2B2B2B;padding:14px 28px;">
          <p style="margin:0;color:#ffffff;font-size:16px;font-weight:bold;">
            {deal.get('address', 'Unknown Address')}
          </p>
          <p style="margin:4px 0 0 0;color:#FFDDAA;font-size:11px;">
            {deal.get('municipality', '')}{case_str}{sqft_str}{built_str}
          </p>
        </td>
      </tr>

      <tr>
        <td style="padding:16px 28px 8px 28px;">
          <span style="display:inline-block;background:{verdict_color};color:#ffffff;
                       font-weight:bold;font-size:14px;padding:6px 18px;border-radius:20px;">
            {verdict or '—'}
          </span>{rating_str}
        </td>
      </tr>

      <tr>
        <td style="padding:8px 28px 16px 28px;">
          <table width="100%" cellpadding="8" cellspacing="0" style="border-collapse:collapse;">
            <tr style="background:#F4F4F4;">
              <td style="border:1px solid #DDDDDD;text-align:center;width:25%;">
                <p style="margin:0;font-size:10px;color:#666666;">SCORE</p>
                <p style="margin:4px 0 0 0;font-size:22px;font-weight:bold;color:#F5A51B;">
                  {deal.get('score', '—')}/100</p>
              </td>
              <td style="border:1px solid #DDDDDD;text-align:center;width:25%;">
                <p style="margin:0;font-size:10px;color:#666666;">MIN BID</p>
                <p style="margin:4px 0 0 0;font-size:16px;font-weight:bold;color:#2B2B2B;">
                  {fmt(deal.get('min_bid'))}</p>
              </td>
              <td style="border:1px solid #DDDDDD;text-align:center;width:25%;">
                <p style="margin:0;font-size:10px;color:#666666;">FMV</p>
                <p style="margin:4px 0 0 0;font-size:16px;font-weight:bold;color:#2B2B2B;">
                  {fmt(deal.get('fmv'))}</p>
              </td>
              <td style="border:1px solid #DDDDDD;text-align:center;width:25%;">
                <p style="margin:0;font-size:10px;color:#666666;">ARV</p>
                <p style="margin:4px 0 0 0;font-size:16px;font-weight:bold;color:#2B2B2B;">
                  {fmt(deal.get('arv'))}</p>
              </td>
            </tr>
            <tr>
              <td style="border:1px solid #DDDDDD;text-align:center;">
                <p style="margin:0;font-size:10px;color:#666666;">FLIP PROFIT</p>
                <p style="margin:4px 0 0 0;font-size:15px;font-weight:bold;color:{flip_color};">
                  {fmt(deal.get('flip_net_profit'))}</p>
              </td>
              <td style="border:1px solid #DDDDDD;text-align:center;">
                <p style="margin:0;font-size:10px;color:#666666;">CAP RATE</p>
                <p style="margin:4px 0 0 0;font-size:15px;font-weight:bold;color:#2B2B2B;">
                  {fmtp(deal.get('cap_rate'))}</p>
              </td>
              <td style="border:1px solid #DDDDDD;text-align:center;">
                <p style="margin:0;font-size:10px;color:#666666;">DSCR</p>
                <p style="margin:4px 0 0 0;font-size:15px;font-weight:bold;color:#2B2B2B;">
                  {dscr_str}</p>
              </td>
              <td style="border:1px solid #DDDDDD;text-align:center;">
                <p style="margin:0;font-size:10px;color:#666666;">MO. NOI</p>
                <p style="margin:4px 0 0 0;font-size:15px;font-weight:bold;color:#2B2B2B;">
                  {fmt(deal.get('monthly_noi'))}</p>
              </td>
            </tr>
          </table>
        </td>
      </tr>

      <tr>
        <td style="padding:0 28px 16px 28px;border-top:1px solid #DDDDDD;">
          <p style="margin:12px 0 6px 0;font-size:12px;font-weight:bold;color:#2B2B2B;
                    text-transform:uppercase;letter-spacing:0.5px;">Red Flags</p>
          {red_flags_block}
        </td>
      </tr>

      {note_block}

      {recommendation_block}

      <tr>
        <td style="background:#F4F4F4;padding:14px 28px;border-top:1px solid #DDDDDD;">
          <p style="margin:0;font-size:11px;color:#888888;text-align:center;">
            Estella Wilson Properties LLC &mdash; Real Estate Investment Analysis<br>
            This analysis is for informational purposes only and does not constitute
            investment advice.
          </p>
        </td>
      </tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""


def _property_section_rows(deal: dict) -> str:
    fmt  = lambda v: f"${v:,.0f}" if v is not None else "—"
    fmtp = lambda v: f"{v:.1f}%" if v is not None else "—"

    verdict = deal.get("verdict", "")
    verdict_color = {"BUY": "#27AE60", "CONSIDER": "#F5A51B",
                     "NO BUY": "#E74C3C", "WATCH": "#F39C12"}.get(verdict, "#666666")

    red_flags_html = "".join(
        f"<li style='color:#E74C3C;margin-bottom:4px;'>&#9888; {f}</li>"
        for f in (deal.get("red_flags") or [])
    )
    red_flags_block = (
        f"<ul style='margin:0;padding-left:20px;'>{red_flags_html}</ul>"
        if red_flags_html
        else "<p style='color:#27AE60;margin:0;'>None identified</p>"
    )

    recommendation = deal.get("recommendation") or deal.get("strategy") or ""
    recommendation_block = ""
    if recommendation:
        recommendation_block = f"""
      <tr>
        <td style="padding:0 28px 16px 28px;border-top:1px solid #DDDDDD;">
          <p style="margin:12px 0 6px 0;font-size:12px;font-weight:bold;color:#2B2B2B;
                    text-transform:uppercase;letter-spacing:0.5px;">Recommendation</p>
          <p style="margin:0;font-size:13px;color:#2B2B2B;line-height:1.5;">{recommendation}</p>
        </td>
      </tr>"""

    sqft_str   = f" &middot; {int(deal['sqft']):,} sqft" if deal.get("sqft") else ""
    built_str  = f" &middot; Built {deal['year_built']}" if deal.get("year_built") else ""
    case_str   = f" &middot; Case {deal['case']}" if deal.get("case") else ""
    rating_str = (f" &nbsp;<span style='font-size:12px;color:#666666;font-weight:bold;'>"
                  f"{deal['perfect_pass_rating']}</span>"
                  if deal.get("perfect_pass_rating") else "")

    flip_color = "#27AE60" if (deal.get("flip_net_profit") or 0) > 0 else "#E74C3C"
    dscr_str   = f"{deal['dscr']:.2f}" if deal.get("dscr") is not None else "—"

    return f"""
      <tr>
        <td style="background:#2B2B2B;padding:14px 28px;border-top:3px solid #F5A51B;">
          <p style="margin:0;color:#ffffff;font-size:16px;font-weight:bold;">
            {deal.get('address', 'Unknown Address')}
          </p>
          <p style="margin:4px 0 0 0;color:#FFDDAA;font-size:11px;">
            {deal.get('municipality', '')}{case_str}{sqft_str}{built_str}
          </p>
        </td>
      </tr>
      <tr>
        <td style="padding:16px 28px 8px 28px;">
          <span style="display:inline-block;background:{verdict_color};color:#ffffff;
                       font-weight:bold;font-size:14px;padding:6px 18px;border-radius:20px;">
            {verdict or '—'}
          </span>{rating_str}
        </td>
      </tr>
      <tr>
        <td style="padding:8px 28px 16px 28px;">
          <table width="100%" cellpadding="8" cellspacing="0" style="border-collapse:collapse;">
            <tr style="background:#F4F4F4;">
              <td style="border:1px solid #DDDDDD;text-align:center;width:25%;">
                <p style="margin:0;font-size:10px;color:#666666;">SCORE</p>
                <p style="margin:4px 0 0 0;font-size:22px;font-weight:bold;color:#F5A51B;">
                  {deal.get('score', '—')}/100</p>
              </td>
              <td style="border:1px solid #DDDDDD;text-align:center;width:25%;">
                <p style="margin:0;font-size:10px;color:#666666;">MIN BID</p>
                <p style="margin:4px 0 0 0;font-size:16px;font-weight:bold;color:#2B2B2B;">
                  {fmt(deal.get('min_bid'))}</p>
              </td>
              <td style="border:1px solid #DDDDDD;text-align:center;width:25%;">
                <p style="margin:0;font-size:10px;color:#666666;">FMV</p>
                <p style="margin:4px 0 0 0;font-size:16px;font-weight:bold;color:#2B2B2B;">
                  {fmt(deal.get('fmv'))}</p>
              </td>
              <td style="border:1px solid #DDDDDD;text-align:center;width:25%;">
                <p style="margin:0;font-size:10px;color:#666666;">ARV</p>
                <p style="margin:4px 0 0 0;font-size:16px;font-weight:bold;color:#2B2B2B;">
                  {fmt(deal.get('arv'))}</p>
              </td>
            </tr>
            <tr>
              <td style="border:1px solid #DDDDDD;text-align:center;">
                <p style="margin:0;font-size:10px;color:#666666;">FLIP PROFIT</p>
                <p style="margin:4px 0 0 0;font-size:15px;font-weight:bold;color:{flip_color};">
                  {fmt(deal.get('flip_net_profit'))}</p>
              </td>
              <td style="border:1px solid #DDDDDD;text-align:center;">
                <p style="margin:0;font-size:10px;color:#666666;">CAP RATE</p>
                <p style="margin:4px 0 0 0;font-size:15px;font-weight:bold;color:#2B2B2B;">
                  {fmtp(deal.get('cap_rate'))}</p>
              </td>
              <td style="border:1px solid #DDDDDD;text-align:center;">
                <p style="margin:0;font-size:10px;color:#666666;">DSCR</p>
                <p style="margin:4px 0 0 0;font-size:15px;font-weight:bold;color:#2B2B2B;">
                  {dscr_str}</p>
              </td>
              <td style="border:1px solid #DDDDDD;text-align:center;">
                <p style="margin:0;font-size:10px;color:#666666;">MO. NOI</p>
                <p style="margin:4px 0 0 0;font-size:15px;font-weight:bold;color:#2B2B2B;">
                  {fmt(deal.get('monthly_noi'))}</p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
      <tr>
        <td style="padding:0 28px 16px 28px;border-top:1px solid #DDDDDD;">
          <p style="margin:12px 0 6px 0;font-size:12px;font-weight:bold;color:#2B2B2B;
                    text-transform:uppercase;letter-spacing:0.5px;">Red Flags</p>
          {red_flags_block}
        </td>
      </tr>
      {recommendation_block}"""


def _build_html_multi(deals: list, sender_name: str, recipient_name: str, **kwargs) -> str:
    n = len(deals)
    sender_line = (
        f"<p style='margin:0 0 4px 0;'>{sender_name} has shared {n} saved properties with you.</p>"
        if sender_name
        else f"<p style='margin:0 0 4px 0;'>{n} saved properties have been shared with you.</p>"
    )

    note = kwargs.get("note", "")
    note_block = ""
    if note:
        note_block = f"""
      <tr>
        <td style="padding:0 28px 16px 28px;border-top:1px solid #DDDDDD;">
          <p style="margin:12px 0 6px 0;font-size:12px;font-weight:bold;color:#2B2B2B;
                    text-transform:uppercase;letter-spacing:0.5px;">Note from Sender</p>
          <p style="margin:0;font-size:13px;color:#2B2B2B;line-height:1.6;
                    background:#F9F9F9;border-left:3px solid #F5A51B;padding:10px 14px;
                    border-radius:0 6px 6px 0;">{note}</p>
        </td>
      </tr>"""

    property_rows = "".join(_property_section_rows(d) for d in deals)

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#F4F4F4;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#F4F4F4;padding:24px 0;">
  <tr><td align="center">
    <table width="600" cellpadding="0" cellspacing="0"
           style="background:#ffffff;border-radius:8px;overflow:hidden;border:1px solid #DDDDDD;">

      <tr>
        <td style="background:#F5A51B;padding:20px 28px;">
          <p style="margin:0;color:#ffffff;font-size:11px;font-weight:bold;
                    letter-spacing:1px;text-transform:uppercase;">
            Estella Wilson Properties LLC
          </p>
          <p style="margin:4px 0 0 0;color:#ffffff;font-size:20px;font-weight:bold;">
            Saved Properties — Investment Analysis
          </p>
        </td>
      </tr>

      <tr>
        <td style="padding:20px 28px 8px 28px;color:#2B2B2B;font-size:14px;
                   border-bottom:1px solid #DDDDDD;">
          <p style="margin:0 0 4px 0;">Hello {recipient_name},</p>
          {sender_line}
          <p style="margin:8px 0 0 0;color:#666666;font-size:12px;">
            The full analysis for all {n} properties is attached as a PDF.
            Key metrics for each are summarized below.
          </p>
        </td>
      </tr>

      {note_block}

      {property_rows}

      <tr>
        <td style="background:#F4F4F4;padding:14px 28px;border-top:1px solid #DDDDDD;">
          <p style="margin:0;font-size:11px;color:#888888;text-align:center;">
            Estella Wilson Properties LLC &mdash; Real Estate Investment Analysis<br>
            This analysis is for informational purposes only and does not constitute
            investment advice.
          </p>
        </td>
      </tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""


def _send_via_resend(subject: str, html_body: str, recipient_name: str,
                     recipient_email: str, pdf_path: Path, pdf_name: str):
    resend.api_key = os.getenv("RESEND_API_KEY")
    with open(pdf_path, "rb") as f:
        pdf_bytes = list(f.read())
    params: resend.Emails.SendParams = {
        "from":        f"{FROM_NAME} <{FROM_EMAIL}>",
        "to":          [f"{recipient_name} <{recipient_email}>"],
        "subject":     subject,
        "html":        html_body,
        "attachments": [{"filename": pdf_name, "content": pdf_bytes}],
    }
    resend.Emails.send(params)


def _send_via_smtp(subject: str, html_body: str, recipient_name: str,
                   recipient_email: str, pdf_path: Path, pdf_name: str):
    host     = os.getenv("SMTP_HOST")
    port     = int(os.getenv("SMTP_PORT", "587"))
    user     = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASS", "")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"]    = f"{FROM_NAME} <{FROM_EMAIL}>"
    msg["To"]      = f"{recipient_name} <{recipient_email}>"
    msg.set_content(
        "See the attached PDF for the full property analysis.",
        subtype="plain",
    )
    msg.add_alternative(html_body, subtype="html")
    with open(pdf_path, "rb") as f:
        msg.add_attachment(f.read(), maintype="application",
                           subtype="pdf", filename=pdf_name)

    smtp_cls = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
    with smtp_cls(host, port, timeout=15) as smtp:
        smtp.ehlo()
        if port != 465:
            smtp.starttls()
            smtp.ehlo()
        if user:
            smtp.login(user, password)
        smtp.send_message(msg)


def _email_backend() -> Optional[str]:
    """The configured email provider: "resend", "smtp", or None."""
    if os.getenv("RESEND_API_KEY"):
        return "resend"
    if os.getenv("SMTP_HOST"):
        return "smtp"
    return None


def _check_can_send(recipient_email: str) -> None:
    """Reject a share that can't succeed before queuing any work, while the
    client can still get a plain HTTP error.

    The 503 below deliberately has no Retry-After header: the frontend retries
    503s that carry one (the database resuming), and retrying can't fix a
    missing email configuration.
    """
    if not _EMAIL_RE.match(recipient_email):
        raise HTTPException(400, "Invalid recipient email address.")
    if _email_backend() is None:
        raise HTTPException(
            503,
            "Email sharing is not configured on this server. "
            "Set RESEND_API_KEY (recommended) or SMTP_HOST/SMTP_USER/SMTP_PASS.",
        )


def _load_deals(sale_ids: list[str]) -> list[dict]:
    """The stored deals being shared, in request order (repeats dropped).

    Raises 404 naming any sale ID that isn't in the deal list. The session is
    closed before the background job starts: the job only needs these plain
    dicts, and a connection held for the job's duration would keep the
    serverless database from pausing.
    """
    unique = list(dict.fromkeys(sale_ids))
    with SessionLocal() as db:
        found = deal_records_by_sale_id(db, unique)
    missing = [sale_id for sale_id in unique if sale_id not in found]
    if missing:
        raise HTTPException(404, f"Deal not found: {', '.join(missing)}")
    return [found[sale_id] for sale_id in unique]


def _deal_from_record(d: dict) -> Deal:
    """Rebuild an analyzed Deal from a stored deal record, for the PDF builder."""
    deal_obj = Deal(
        sale_id      = str(d.get("sale_id") or ""),
        case         = str(d.get("case") or ""),
        address      = str(d.get("address") or "Unknown"),
        municipality = str(d.get("municipality") or ""),
        parcel       = str(d.get("parcel") or ""),
        min_bid      = float(d.get("min_bid") or 0),
        tax_bid      = float(d.get("tax_bid") or 0),
        fmv          = float(d.get("fmv") or 0),
        assessed     = float(d.get("assessed") or 0),
        year_built   = int(d.get("year_built") or 1950),
        sqft         = int(d.get("sqft") or 1000),
        bedrooms     = int(d.get("bedrooms") or 3),
    )
    # Copy the stored analysis results (verdict, score, projections…) onto it.
    for key, val in d.items():
        if hasattr(deal_obj, key):
            try:
                setattr(deal_obj, key, val)
            except Exception:
                pass
    return deal_obj


def _send(subject: str, html_body: str, req: ShareRequest, pdf_path: Path, pdf_name: str) -> None:
    """Send through the configured provider. Delivery failures become JobErrors,
    so the polling client sees a readable reason."""
    try:
        if _email_backend() == "resend":
            _send_via_resend(subject, html_body, req.recipient_name,
                             req.recipient_email, pdf_path, pdf_name)
        else:
            _send_via_smtp(subject, html_body, req.recipient_name,
                           req.recipient_email, pdf_path, pdf_name)
    except smtplib.SMTPAuthenticationError as exc:
        raise JobError("SMTP authentication failed. Check SMTP_USER and SMTP_PASS.") from exc
    except smtplib.SMTPRecipientsRefused as exc:
        raise JobError("Recipient address was rejected by the mail server.") from exc
    except Exception as exc:
        log.exception("Sending a share email failed")
        raise JobError(f"Failed to send email: {exc}") from exc


def _run_share_property(job_id: str, req: SharePropertyRequest, record: dict) -> None:
    update_job(job_id, "running", 20, "Building PDF report…")
    ts        = utcnow().strftime("%Y%m%d_%H%M%S")
    safe_addr = "".join(c if c.isalnum() else "_" for c in str(record.get("address", "property"))[:30])
    pdf_name  = f"Share_{safe_addr}_{ts}.pdf"
    # The PDF only exists to be attached, so it's built in a per-job
    # temporary directory that's removed afterwards. It used to be written to
    # the shared reports folder, where two shares in the same second collided.
    with tempfile.TemporaryDirectory(prefix="share-") as workdir:
        pdf_path = Path(workdir) / pdf_name
        build_and_save_pdf(
            [_deal_from_record(record)],
            pdf_path,
            report_title=f"Property Analysis — {record.get('address', '')}",
            skip_cover=True,
        )

        update_job(job_id, "running", 70, "Sending email…")
        subject   = (f"Property Analysis: {record.get('address', 'Property')} "
                     f"[{record.get('verdict', '')}]").replace("\n", " ").replace("\r", " ")
        html_body = _build_html(record, req.sender_name or "", req.recipient_name,
                                note=req.note or "")
        _send(subject, html_body, req, pdf_path, pdf_name)

    complete_job(job_id, f"Sent to {req.recipient_email}",
                 result={"recipient": req.recipient_email, "count": 1})


def _run_share_favorites(job_id: str, req: ShareFavoritesRequest, records: list[dict]) -> None:
    count = len(records)
    update_job(job_id, "running", 20, f"Building PDF report for {count} properties…")
    ts       = utcnow().strftime("%Y%m%d_%H%M%S")
    pdf_name = f"SavedProperties_{ts}.pdf"

    # Built in a per-job temporary directory, like _run_share_property above.
    with tempfile.TemporaryDirectory(prefix="share-") as workdir:
        pdf_path = Path(workdir) / pdf_name
        build_and_save_pdf(
            [_deal_from_record(record) for record in records],
            pdf_path,
            report_title=f"Saved Properties — {count} Selected",
            skip_cover=False,
        )

        update_job(job_id, "running", 70, "Sending email…")
        subject   = f"Saved Properties Analysis — {count} Properties"
        html_body = _build_html_multi(records, req.sender_name or "",
                                      req.recipient_name, note=req.note or "")
        _send(subject, html_body, req, pdf_path, pdf_name)

    complete_job(job_id, f"Sent to {req.recipient_email}",
                 result={"recipient": req.recipient_email, "count": count})


# Both share endpoints validate and load deals inline (fast), then build the PDF
# and send the email in a background job. PDF rendering plus the email
# provider's response time could outlast the 45-second limit Static Web Apps
# puts on proxied API requests. Poll GET /api/jobs/{job_id}; the finished job's
# result is {"recipient": ..., "count": ...}.

@router.post("/property", response_model=JobStarted)
def share_property(req: SharePropertyRequest, background_tasks: BackgroundTasks):
    _check_can_send(req.recipient_email)
    [record] = _load_deals([req.sale_id])
    job_id = create_job()
    background_tasks.add_task(run_job, job_id, "Share failed", _run_share_property, req, record)
    return JobStarted(job_id=job_id)


@router.post("/favorites", response_model=JobStarted)
def share_favorites(req: ShareFavoritesRequest, background_tasks: BackgroundTasks):
    _check_can_send(req.recipient_email)
    records = _load_deals(req.sale_ids)
    job_id = create_job()
    background_tasks.add_task(run_job, job_id, "Share failed", _run_share_favorites, req, records)
    return JobStarted(job_id=job_id)
