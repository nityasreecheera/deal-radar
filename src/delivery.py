"""
Getting the digest to a human.

Email over SMTP, or Slack through Hermes. A radar you have to remember to open is
a radar you check twice and then forget, so delivery is not a nice-to-have — it
is the difference between a tool and a folder of files.

Everything here reports failure by returning it rather than raising. A run whose
real work succeeded — extending the seen-index — should not be recorded as failed
because a mail server was briefly unreachable.
"""

from __future__ import annotations

import os
import shutil
import smtplib
import subprocess
from email.message import EmailMessage
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, Field


PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Port 587 with STARTTLS. Oracle Cloud blocks outbound port 25, so plain SMTP is
# not an option from this machine even if a server would accept it.
DEFAULT_SMTP_HOST = "smtp.gmail.com"
DEFAULT_SMTP_PORT = 587

# A sender takes a built message and delivers it. Injectable so tests never open
# a socket.
MessageSender = Callable[[EmailMessage], None]


class EmailSettings(BaseModel):
    """SMTP configuration, read from the environment."""

    host: str = DEFAULT_SMTP_HOST
    port: int = Field(default=DEFAULT_SMTP_PORT, ge=1, le=65535)
    user: str = Field(min_length=1)
    password: str = Field(min_length=1)
    recipient: str = Field(min_length=1)
    sender: str = Field(min_length=1)


def load_email_settings() -> EmailSettings | None:
    """
    Read SMTP settings, returning None when email is not configured.

    Absence is a valid state, not an error: the radar is useful before delivery
    is set up, and a missing password should not look like a crash.
    """
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")

    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")

    if not user or not password:
        return None

    return EmailSettings(
        host=os.getenv("SMTP_HOST", DEFAULT_SMTP_HOST),
        port=int(os.getenv("SMTP_PORT", str(DEFAULT_SMTP_PORT))),
        user=user,
        password=password,
        # Sending to yourself is the common case, so both default to the account.
        recipient=os.getenv("DIGEST_EMAIL_TO", user),
        sender=os.getenv("DIGEST_EMAIL_FROM", user),
    )


def build_message(
    content: str,
    subject: str,
    settings: EmailSettings,
) -> EmailMessage:
    """
    Build the email.

    Plain text on purpose. The digest is already laid out for reading, HTML would
    add nothing, and plain text renders identically on a phone at breakfast as it
    does anywhere else.
    """
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.sender
    message["To"] = settings.recipient
    message.set_content(content)

    return message


def create_smtp_sender(settings: EmailSettings) -> MessageSender:
    """Build a sender that talks to a real SMTP server over STARTTLS."""

    def send(message: EmailMessage) -> None:
        with smtplib.SMTP(settings.host, settings.port, timeout=30) as server:
            server.starttls()
            server.login(settings.user, settings.password)
            server.send_message(message)

    return send


def send_email(
    content: str,
    subject: str,
    settings: EmailSettings | None = None,
    send: MessageSender | None = None,
) -> tuple[bool, str]:
    """Deliver the digest by email. Returns whether it sent, and why not."""
    resolved = settings or load_email_settings()

    if resolved is None:
        return False, "email is not configured (SMTP_USER / SMTP_PASSWORD unset)"

    message = build_message(content, subject, resolved)
    sender = send or create_smtp_sender(resolved)

    try:
        sender(message)
    except smtplib.SMTPAuthenticationError:
        return (
            False,
            "SMTP rejected the credentials. For Gmail this must be an App "
            "Password, not the account password.",
        )
    except (smtplib.SMTPException, OSError) as exc:
        return False, f"email failed: {exc}"

    return True, f"emailed {resolved.recipient}"


def send_to_slack(content: str, target: str = "slack") -> tuple[bool, str]:
    """
    Deliver through Hermes, which already holds messaging credentials.

    Reusing `hermes send` avoids creating and credentialing a second Slack app
    for one message a day.
    """
    hermes = shutil.which("hermes")

    if hermes is None:
        return False, "hermes is not on PATH, so the digest was not sent"

    try:
        result = subprocess.run(
            [hermes, "send", "-t", target],
            input=content,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "hermes send timed out"

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()

        return False, f"hermes send failed: {detail[:200]}"

    return True, f"sent to {target}"


def deliver(
    content: str,
    subject: str,
    prefer_slack: bool = False,
) -> tuple[bool, str]:
    """
    Send the digest by whatever is configured.

    Email is tried first because it needs no workspace and no admin approval.
    Slack is the fallback rather than the default for the same reason.
    """
    if not prefer_slack:
        sent, message = send_email(content, subject)

        if sent:
            return True, message

        email_problem = message
    else:
        email_problem = "email not attempted"

    sent, slack_message = send_to_slack(content)

    if sent:
        return True, slack_message

    return False, f"{email_problem}; {slack_message}"
