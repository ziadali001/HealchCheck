#!/usr/bin/env python3
"""Email the generated EMICOOL report through the configured SMTP relay."""

import base64
import datetime
import html
import io
import json
import os
import re
import smtplib
import ssl
import sys
import zipfile
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    CAIRO = ZoneInfo("Africa/Cairo")
except Exception:
    CAIRO = datetime.timezone.utc

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
CUSTOMER_NAME = "EMICOOL"

# ZainTech brand palette (kept in sync with the HTML report).
NAVY = "#2B5AA8"
NAVY_DEEP = "#0f2550"
ACCENT = "#00C2FF"
TEXT = "#1A2740"
MUTED = "#5A6E8A"
BORDER = "#D6E4F5"
OFFWHITE = "#F5F8FC"
SUCCESS = "#0C9B6E"
WARNING = "#D97706"
DANGER = "#C0392B"

SEVERITY_COLORS = {"high": DANGER, "medium": WARNING, "low": NAVY}


def required_environment(name):
    """Return an environment value or stop without revealing sensitive data."""
    value = os.environ.get(name, "").strip()
    if not value:
        print(
            f"::error title=Missing email configuration::{name} is required. "
            "See README.md for GitHub Actions setup.",
            file=sys.stderr,
        )
        sys.exit(1)
    return value


def report_attachments():
    """Find the HTML and JSON reports produced for the EMICOOL profile."""
    reports_directory = Path("reports")
    patterns = (
        "OCI_Health_Report_EMICOOL_*.html",
        "OCI_Health_Report_EMICOOL_*.json",
    )
    attachments = [
        report
        for pattern in patterns
        for report in sorted(reports_directory.glob(pattern))
    ]
    if len(attachments) != 2:
        print(
            "::error title=Report attachments not found::Expected one EMICOOL "
            "HTML report and one EMICOOL JSON report in reports/.",
            file=sys.stderr,
        )
        sys.exit(1)
    return attachments


def zip_reports(reports):
    """Bundle the reports into one in-memory zip named after the HTML report."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for report in reports:
            archive.write(report, arcname=report.name)
    html_report = next(report for report in reports if report.suffix == ".html")
    return buffer.getvalue(), f"{html_report.stem}.zip"


def zaintech_logo():
    """Reuse the white ZainTech logo already embedded in the report script."""
    source = (REPOSITORY_ROOT / "oci_health_check.py").read_text(encoding="utf-8")
    match = re.search(r'^ZAINTECH_LOGO_BASE64 = "([^"]+)"', source, re.MULTILINE)
    return base64.b64decode(match.group(1)) if match else None


def load_report_data(reports):
    json_report = next(report for report in reports if report.suffix == ".json")
    try:
        return json.loads(json_report.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def report_date(data):
    """Report generation time in Cairo local time."""
    generated = data.get("metadata", {}).get("generated_at")
    try:
        moment = datetime.datetime.fromisoformat(generated)
    except (TypeError, ValueError):
        moment = datetime.datetime.now(datetime.timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=datetime.timezone.utc)
    return moment.astimezone(CAIRO)


def format_cost(summary):
    total = summary.get("cost_total")
    # A failed Usage API call leaves cost_total at 0; don't report that
    # as a real zero spend.
    if (
        not isinstance(total, (int, float))
        or str(summary.get("cost_status", "")).upper() != "COLLECTED"
    ):
        return "Not available"
    currency = summary.get("cost_currency", "USD")
    days = summary.get("cost_period_days")
    period = f" ({days} days)" if days else ""
    return f"{currency} {total:,.2f}{period}"


def key_metrics(summary):
    """(label, value, highlight colour or None) rows for the email body."""

    def count(key):
        value = summary.get(key, 0)
        return len(value) if isinstance(value, list) else (value or 0)

    def flagged(key):
        return DANGER if count(key) else None

    return [
        ("Regions scanned", count("regions_scanned"), None),
        ("Total resources", count("total_resources"), None),
        ("Running / stopped VMs",
         f"{count('running_vms')} / {count('stopped_vms')}",
         WARNING if count("stopped_vms") else None),
        ("Firing alarms", count("firing_alarms"), flagged("firing_alarms")),
        ("Backup issues", count("backup_issues"), flagged("backup_issues")),
        ("Cloud Guard problems", count("cloud_guard_problems"),
         flagged("cloud_guard_problems")),
        ("High-priority recommendations",
         count("high_priority_recommendations"),
         flagged("high_priority_recommendations")),
        ("Cost", format_cost(summary), None),
    ]


def build_html(data, report_day, logo_cid):
    summary = data.get("summary", {})
    status = str(summary.get("overall_status", "UNKNOWN")).upper()
    status_color = SUCCESS if status == "HEALTHY" else WARNING
    esc = html.escape

    logo_html = (
        f'<img src="cid:{logo_cid[1:-1]}" alt="ZainTech" width="180" '
        'style="display:block;width:180px;max-width:180px;height:auto;border:0;">'
        if logo_cid
        else '<span style="color:#ffffff;font-size:22px;font-weight:bold;">ZainTech</span>'
    )

    metric_rows = "".join(
        f"""
        <tr>
          <td style="padding:10px 14px;border-bottom:1px solid {BORDER};color:{MUTED};font-size:14px;">{esc(label)}</td>
          <td align="right" style="padding:10px 14px;border-bottom:1px solid {BORDER};color:{color or TEXT};font-size:14px;font-weight:bold;">{esc(str(value))}</td>
        </tr>"""
        for label, value, color in key_metrics(summary)
    )

    recommendations = [
        r for r in data.get("recommendations", [])
        if r.get("severity") in ("high", "medium")
    ][:5]
    if recommendations:
        items = "".join(
            f"""
            <tr>
              <td valign="top" style="padding:8px 0;width:72px;">
                <span style="display:inline-block;padding:2px 8px;border-radius:10px;background:{SEVERITY_COLORS.get(r['severity'], NAVY)};color:#ffffff;font-size:11px;font-weight:bold;text-transform:uppercase;">{esc(r['severity'])}</span>
              </td>
              <td style="padding:8px 0;color:{TEXT};font-size:14px;">{esc(r.get('title', ''))}</td>
            </tr>"""
            for r in recommendations
        )
        recommendations_html = f"""
          <h3 style="margin:28px 0 8px;color:{NAVY_DEEP};font-size:16px;">Items requiring attention</h3>
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0">{items}</table>"""
    else:
        recommendations_html = f"""
          <p style="margin:28px 0 0;color:{TEXT};font-size:14px;">No high or medium priority items were identified in this run.</p>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(CUSTOMER_NAME)} OCI Daily Health Report</title>
</head>
<body style="margin:0;padding:0;background:{OFFWHITE};font-family:Segoe UI,Arial,Helvetica,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{OFFWHITE};">
  <tr>
    <td align="center" style="padding:24px 12px;">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px;background:#ffffff;border:1px solid {BORDER};border-radius:8px;overflow:hidden;">
        <tr>
          <td style="background:{NAVY_DEEP};padding:24px 32px;border-bottom:4px solid {ACCENT};">
            {logo_html}
          </td>
        </tr>
        <tr>
          <td style="padding:32px;">
            <p style="margin:0 0 4px;color:{MUTED};font-size:12px;letter-spacing:1px;text-transform:uppercase;">Managed Cloud Services</p>
            <h1 style="margin:0 0 6px;color:{NAVY_DEEP};font-size:22px;">{esc(CUSTOMER_NAME)} &ndash; OCI Daily Health Report</h1>
            <p style="margin:0 0 24px;color:{MUTED};font-size:14px;">{esc(report_day.strftime('%A, %d %B %Y'))} &middot; generated {esc(report_day.strftime('%H:%M'))} Cairo time</p>

            <p style="margin:0 0 16px;color:{TEXT};font-size:14px;line-height:1.6;">Dear Team,</p>
            <p style="margin:0 0 24px;color:{TEXT};font-size:14px;line-height:1.6;">Please find below the summary of today's health check of the {esc(CUSTOMER_NAME)} Oracle Cloud Infrastructure tenancy. The full report is attached.</p>

            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
              <tr>
                <td style="background:{OFFWHITE};border-left:4px solid {status_color};padding:14px 18px;border-radius:4px;">
                  <span style="color:{MUTED};font-size:13px;">Overall status</span><br>
                  <span style="color:{status_color};font-size:20px;font-weight:bold;">{esc(status)}</span>
                </td>
              </tr>
            </table>

            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid {BORDER};border-radius:6px;border-collapse:separate;">
              {metric_rows}
            </table>
            {recommendations_html}

            <p style="margin:28px 0 0;color:{TEXT};font-size:14px;line-height:1.6;">The attached archive contains the detailed HTML report (open in any browser) and the raw JSON data.</p>
            <p style="margin:24px 0 0;color:{TEXT};font-size:14px;line-height:1.6;">Best regards,<br><strong>ZainTech Cloud Operations</strong></p>
          </td>
        </tr>
        <tr>
          <td style="background:{OFFWHITE};padding:16px 32px;border-top:1px solid {BORDER};color:{MUTED};font-size:11px;line-height:1.5;">
            This is an automated message generated by the ZainTech OCI health check service. Please do not reply directly to this email.
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
</body>
</html>"""


def build_text(data, report_day):
    summary = data.get("summary", {})
    status = str(summary.get("overall_status", "UNKNOWN")).upper()
    lines = [
        "Dear Team,",
        "",
        f"Please find below the summary of today's health check of the "
        f"{CUSTOMER_NAME} Oracle Cloud Infrastructure tenancy "
        f"({report_day.strftime('%d %B %Y')}). The full report is attached.",
        "",
        f"Overall status: {status}",
        "",
    ]
    lines += [f"  {label}: {value}" for label, value, _ in key_metrics(summary)]
    lines += [
        "",
        "Best regards,",
        "ZainTech Cloud Operations",
        "",
        "This is an automated message. Please do not reply directly.",
    ]
    return "\n".join(lines)


def main():
    recipient = required_environment("REPORT_TEST_RECIPIENT")
    sender = required_environment("REPORT_SENDER")
    smtp_host = required_environment("SMTP_HOST")
    smtp_username = required_environment("SMTP_USERNAME")
    smtp_password = required_environment("SMTP_PASSWORD")
    smtp_port_text = os.environ.get("SMTP_PORT", "587").strip() or "587"

    try:
        smtp_port = int(smtp_port_text)
    except ValueError:
        print(
            "::error title=Invalid SMTP port::SMTP_PORT must be a number.",
            file=sys.stderr,
        )
        sys.exit(1)

    attachments = report_attachments()
    data = load_report_data(attachments)
    report_day = report_date(data)
    status = str(data.get("summary", {}).get("overall_status", "UNKNOWN")).upper()

    logo = zaintech_logo()
    logo_cid = make_msgid(domain="zaintech.com") if logo else None

    message = EmailMessage()
    message["Subject"] = (
        f"{CUSTOMER_NAME} | OCI Daily Health Report | "
        f"{report_day.strftime('%d %b %Y')} | {status}"
    )
    message["From"] = f"ZainTech Cloud Operations <{sender}>"
    message["To"] = recipient
    message.set_content(build_text(data, report_day))
    message.add_alternative(build_html(data, report_day, logo_cid), subtype="html")

    if logo:
        message.get_payload()[1].add_related(
            logo,
            maintype="image",
            subtype="png",
            cid=logo_cid,
            filename="zaintech-logo.png",
        )

    zip_bytes, zip_name = zip_reports(attachments)
    message.add_attachment(
        zip_bytes,
        maintype="application",
        subtype="zip",
        filename=zip_name,
    )

    if os.environ.get("EMAIL_DRY_RUN"):
        Path(os.environ["EMAIL_DRY_RUN"]).write_bytes(bytes(message))
        print(f"Dry run: message written to {os.environ['EMAIL_DRY_RUN']}.")
        return

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
            smtp.login(smtp_username, smtp_password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        print(
            f"::error title=Email was not sent::{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(
        f"Email sent to {recipient} with {zip_name} "
        f"({len(attachments)} report(s), {len(zip_bytes)} bytes)."
    )


if __name__ == "__main__":
    main()
