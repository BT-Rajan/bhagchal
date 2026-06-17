"""
Mail delivery for post-game reports.

Behavior is controlled by Config.MAIL_MODE:
- 'development' (default): nothing is actually sent. A plain-text file
  describing the email (To/From/Subject/Body) is written under
  Config.MAIL_DIR, named after the report file, so you can inspect what
  would have been sent without configuring real SMTP credentials.
- 'production': sends a real email via SMTP using Config.SMTP_* settings.

All settings are read from environment variables (see .env / README).
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from config import Config


class MailError(Exception):
    """Raised when an email could not be sent (production mode only)."""


def _recipients(report):
    """
    Build the recipient list: the player's own registered email (if known)
    plus any extra/admin recipients configured via MAIL_TO.
    """
    recipients = []

    username = report.get('username')
    if username:
        try:
            from models.user import user_model
            user = user_model.get_user(username)
            if user and user.get('email'):
                recipients.append(user['email'])
        except Exception:
            pass

    if Config.MAIL_TO:
        recipients.extend(addr.strip() for addr in Config.MAIL_TO.split(',') if addr.strip())

    # De-duplicate while preserving order
    seen = set()
    deduped = []
    for addr in recipients:
        if addr not in seen:
            seen.add(addr)
            deduped.append(addr)
    return deduped


def _build_body(report, analysis_text):
    final = report.get('final_state', {})
    lines = [
        f"Game report for: {report.get('username')}",
        f"Result: {report.get('status')}",
        f"Role played: {report.get('human_role')}  |  Mode: {report.get('mode')}  |  Difficulty: {report.get('difficulty')}",
        f"Total moves: {report.get('total_moves')}  |  Duration: {report.get('duration_seconds')}s",
        f"Goats captured: {final.get('goats_captured')}  |  Goats placed: {final.get('goats_placed')}",
        "",
        "=" * 60,
        "PLAYER PERSONALITY ANALYSIS",
        "=" * 60,
        analysis_text or "(analysis unavailable)",
    ]
    return "\n".join(lines)


def send_report_email(report, analysis_text, report_path):
    """
    Send (or, in development, mock-send) the analyzed report by email.
    Never raises in development mode; raises MailError on failure in
    production mode so the caller can log it.
    """
    subject = f"Bagh Chal Report - {report.get('username', 'unknown')} - {report.get('status', 'finished')}"
    body = _build_body(report, analysis_text)
    recipients = _recipients(report)

    if Config.MAIL_MODE != 'production':
        _write_dev_mail_log(report_path, subject, recipients, body)
        return

    if not recipients:
        raise MailError("No recipients resolved (no registered email and no MAIL_TO configured).")
    if not Config.SMTP_HOST:
        raise MailError("SMTP_HOST not configured.")

    msg = MIMEMultipart()
    msg['From'] = Config.MAIL_FROM
    msg['To'] = ', '.join(recipients)
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT, timeout=20) as server:
            if Config.SMTP_USE_TLS:
                server.starttls()
            if Config.SMTP_USERNAME:
                server.login(Config.SMTP_USERNAME, Config.SMTP_PASSWORD)
            server.sendmail(Config.MAIL_FROM, recipients, msg.as_string())
    except (smtplib.SMTPException, OSError) as e:
        raise MailError(f"Failed to send report email: {e}") from e


def _write_dev_mail_log(report_path, subject, recipients, body):
    """Write a .log file describing the 'sent' email, named after the report."""
    if not os.path.exists(Config.MAIL_DIR):
        os.makedirs(Config.MAIL_DIR)

    base = os.path.splitext(os.path.basename(report_path))[0]
    log_path = os.path.join(Config.MAIL_DIR, f"{base}.log")

    content = (
        f"To: {', '.join(recipients) if recipients else '(no recipient resolved)'}\n"
        f"From: {Config.MAIL_FROM}\n"
        f"Subject: {subject}\n"
        f"{'-' * 60}\n"
        f"{body}\n"
    )
    with open(log_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return log_path
