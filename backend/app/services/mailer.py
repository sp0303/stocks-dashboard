"""Tiny SMTP mailer for watchlist alerts.

Gmail SMTP over STARTTLS. The sending account (alert_email_from / alert_smtp_user)
needs a Gmail *App Password* — a regular password is rejected by Google for SMTP.
smtplib is blocking, so callers should invoke send_email via asyncio.to_thread.
"""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from app.config import settings


class MailNotConfigured(RuntimeError):
    pass


def send_email(to: str, subject: str, body: str) -> None:
    """Send a plaintext email. Raises MailNotConfigured if no app password is set,
    or smtplib errors on transport/auth failure (caller decides how to log)."""
    password = settings.alert_smtp_password.strip()
    if not password:
        raise MailNotConfigured("alert_smtp_password is not configured")
    user = (settings.alert_smtp_user or settings.alert_email_from).strip()

    msg = EmailMessage()
    msg["From"] = settings.alert_email_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(settings.alert_smtp_host, settings.alert_smtp_port, timeout=20) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.login(user, password)
        smtp.send_message(msg)
