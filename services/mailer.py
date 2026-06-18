"""
Mail delivery for post-game Cogzi behavioral reports.

Behavior is controlled by Config.MAIL_MODE:
- 'development' (default): nothing is actually sent. A plain-text .log
  file describing the email (To/From/Subject/Body) is written under
  Config.MAIL_DIR, and the generated PDF is copied alongside it, so you
  can inspect exactly what would have been sent without configuring real
  SMTP credentials.
- 'production': sends a real email via SMTP using Config.SMTP_* settings,
  with the PDF attached.

All settings are read from environment variables (see .env / README).
"""
import os
import shutil
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

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


def _build_body(report):
    return (
        f"Hi {report.get('username', '')},\n\n"
        f"Your {Config.COGZI_MODEL_NAME} behavioral assessment for game "
        f"{report.get('game_id', '')} is attached as a PDF.\n\n"
        f"Result: {report.get('status', '-')}\n"
        f"This assessment is based on limited samples; ask your administrator "
        f"for more samples to get more precise results.\n"
    )


def send_report_email(report, profile, pdf_path):
    """
    Send (or, in development, mock-send) the Cogzi behavioral report PDF by
    email. Never raises in development mode; raises MailError on failure in
    production mode so the caller can log it.
    """
    subject = f"{Config.COGZI_MODEL_NAME} Report - {report.get('username', 'unknown')} - {report.get('status', 'finished')}"
    body = _build_body(report)
    recipients = _recipients(report)

    if Config.MAIL_MODE != 'production':
        _write_dev_mail_log(pdf_path, subject, recipients, body)
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

    if pdf_path and os.path.exists(pdf_path):
        with open(pdf_path, 'rb') as f:
            attachment = MIMEApplication(f.read(), _subtype='pdf')
        attachment.add_header(
            'Content-Disposition', 'attachment', filename=os.path.basename(pdf_path)
        )
        msg.attach(attachment)

    try:
        with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT, timeout=20) as server:
            if Config.SMTP_USE_TLS:
                server.starttls()
            if Config.SMTP_USERNAME:
                server.login(Config.SMTP_USERNAME, Config.SMTP_PASSWORD)
            server.sendmail(Config.MAIL_FROM, recipients, msg.as_string())
    except (smtplib.SMTPException, OSError) as e:
        raise MailError(f"Failed to send report email: {e}") from e


def _write_dev_mail_log(pdf_path, subject, recipients, body):
    """Write a .log describing the 'sent' email and copy the PDF alongside it."""
    if not os.path.exists(Config.MAIL_DIR):
        os.makedirs(Config.MAIL_DIR)

    base = os.path.splitext(os.path.basename(pdf_path))[0] if pdf_path else 'report'
    log_path = os.path.join(Config.MAIL_DIR, f"{base}.log")

    attachment_name = os.path.basename(pdf_path) if pdf_path else '(none)'
    content = (
        f"To: {', '.join(recipients) if recipients else '(no recipient resolved)'}\n"
        f"From: {Config.MAIL_FROM}\n"
        f"Subject: {subject}\n"
        f"Attachment: {attachment_name}\n"
        f"{'-' * 60}\n"
        f"{body}\n"
    )
    with open(log_path, 'w', encoding='utf-8') as f:
        f.write(content)

    if pdf_path and os.path.exists(pdf_path):
        shutil.copy(pdf_path, os.path.join(Config.MAIL_DIR, os.path.basename(pdf_path)))

    return log_path
