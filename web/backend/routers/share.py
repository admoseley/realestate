import os
import re
import sys
import smtplib
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

import resend
from fastapi import APIRouter, HTTPException

sys.path.insert(0, str(Path(__file__).parents[3]))

from investment_analyzer import Deal
from generate_pdf_report import build_and_save_pdf
from models import SharePropertyRequest

router = APIRouter(prefix="/api/share", tags=["share"])

REPORTS_DIR = Path(os.getenv("REPORTS_DIR", str(Path(__file__).parent.parent / "reports")))
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

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
        f"See the attached PDF for the full property analysis.",
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


@router.post("/property")
def share_property(req: SharePropertyRequest):
    if not _EMAIL_RE.match(req.recipient_email):
        raise HTTPException(400, "Invalid recipient email address.")

    use_resend = bool(os.getenv("RESEND_API_KEY"))
    use_smtp   = bool(os.getenv("SMTP_HOST"))

    if not use_resend and not use_smtp:
        raise HTTPException(
            503,
            "Email sharing is not configured on this server. "
            "Set RESEND_API_KEY (recommended) or SMTP_HOST/SMTP_USER/SMTP_PASS.",
        )

    d = req.deal
    try:
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
        for key, val in d.items():
            if hasattr(deal_obj, key):
                try:
                    setattr(deal_obj, key, val)
                except Exception:
                    pass
    except Exception as exc:
        raise HTTPException(422, f"Invalid deal data: {exc}")

    ts        = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_addr = "".join(c if c.isalnum() else "_" for c in str(d.get("address", "property"))[:30])
    pdf_name  = f"Share_{safe_addr}_{ts}.pdf"
    pdf_path  = REPORTS_DIR / pdf_name

    try:
        build_and_save_pdf(
            [deal_obj],
            pdf_path,
            report_title=f"Property Analysis — {d.get('address', '')}",
            skip_cover=True,
        )

        subject   = (f"Property Analysis: {d.get('address', 'Property')} "
                     f"[{d.get('verdict', '')}]").replace("\n", " ").replace("\r", " ")
        html_body = _build_html(d, req.sender_name or "", req.recipient_name,
                                note=req.note or "")

        try:
            if use_resend:
                _send_via_resend(subject, html_body, req.recipient_name,
                                 req.recipient_email, pdf_path, pdf_name)
            else:
                _send_via_smtp(subject, html_body, req.recipient_name,
                               req.recipient_email, pdf_path, pdf_name)
        except smtplib.SMTPAuthenticationError:
            raise HTTPException(500, "SMTP authentication failed. Check SMTP_USER and SMTP_PASS.")
        except smtplib.SMTPRecipientsRefused:
            raise HTTPException(400, "Recipient address was rejected by the mail server.")
        except Exception as exc:
            raise HTTPException(500, f"Failed to send email: {exc}")

    finally:
        try:
            pdf_path.unlink(missing_ok=True)
        except Exception:
            pass

    return {"status": "sent", "recipient": req.recipient_email}
