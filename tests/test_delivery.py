import smtplib
from email.message import EmailMessage

from src.delivery import (
    EmailSettings,
    build_message,
    deliver,
    send_email,
)


def settings(**overrides) -> EmailSettings:
    data = {
        "user": "me@example.com",
        "password": "app-password",
        "recipient": "me@example.com",
        "sender": "me@example.com",
    }
    data.update(overrides)

    return EmailSettings(**data)


def capture():
    """A sender that records the message instead of sending it."""
    sent: list[EmailMessage] = []

    def send(message: EmailMessage) -> None:
        sent.append(message)

    return sent, send


def test_message_is_plain_text() -> None:
    message = build_message("body text", "Deal Radar · 2 new", settings())

    assert message["Subject"] == "Deal Radar · 2 new"
    assert message["From"] == "me@example.com"
    assert message["To"] == "me@example.com"
    assert message.get_content_type() == "text/plain"
    assert "body text" in message.get_content()


def test_recipient_and_sender_can_differ() -> None:
    message = build_message(
        "body",
        "subject",
        settings(recipient="analyst@fund.com", sender="radar@example.com"),
    )

    assert message["To"] == "analyst@fund.com"
    assert message["From"] == "radar@example.com"


def test_send_email_reports_success() -> None:
    sent, sender = capture()

    ok, message = send_email("digest", "subject", settings(), send=sender)

    assert ok is True
    assert "me@example.com" in message
    assert len(sent) == 1


def test_send_email_without_configuration_is_not_a_crash(monkeypatch) -> None:
    # Absence of email settings is a valid state, not an error.
    #
    # load_email_settings is patched rather than left to the environment. Without
    # this the test passes on a machine with no .env and, on a machine that has
    # one, silently sends a real email — which it did on the deployment host
    # before this was fixed. A test must not depend on ambient configuration,
    # and must never reach the outside world.
    monkeypatch.setattr("src.delivery.load_email_settings", lambda: None)

    ok, message = send_email("digest", "subject", settings=None, send=None)

    assert ok is False
    assert "not configured" in message


def test_an_authentication_failure_names_the_likely_cause() -> None:
    def rejecting(message: EmailMessage) -> None:
        raise smtplib.SMTPAuthenticationError(535, b"denied")

    ok, message = send_email("digest", "subject", settings(), send=rejecting)

    assert ok is False
    # The Gmail App Password trap is the single most common cause here.
    assert "App Password" in message


def test_a_transport_failure_is_reported_not_raised() -> None:
    def failing(message: EmailMessage) -> None:
        raise OSError("network unreachable")

    ok, message = send_email("digest", "subject", settings(), send=failing)

    assert ok is False
    assert "network unreachable" in message


def test_an_smtp_error_is_reported_not_raised() -> None:
    def failing(message: EmailMessage) -> None:
        raise smtplib.SMTPServerDisconnected("gone")

    ok, message = send_email("digest", "subject", settings(), send=failing)

    assert ok is False
    assert "email failed" in message


def test_settings_reject_an_impossible_port() -> None:
    try:
        EmailSettings(
            user="a@b.com",
            password="x",
            recipient="a@b.com",
            sender="a@b.com",
            port=70000,
        )
    except Exception:
        return

    raise AssertionError("a port above 65535 should be rejected")


def test_deliver_reports_both_failures_when_nothing_is_configured(
    monkeypatch,
) -> None:
    # With neither email nor Slack available, the caller needs to know both
    # reasons rather than just the last one.
    monkeypatch.setattr("src.delivery.load_email_settings", lambda: None)
    monkeypatch.setattr("src.delivery.shutil.which", lambda name: None)

    ok, message = deliver("digest", "subject")

    assert ok is False
    assert "not configured" in message
    assert "hermes" in message


def test_deliver_prefers_email(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.delivery.send_email",
        lambda content, subject: (True, "emailed you"),
    )

    def slack_should_not_run(content, target="slack"):
        raise AssertionError("Slack was tried even though email succeeded")

    monkeypatch.setattr("src.delivery.send_to_slack", slack_should_not_run)

    ok, message = deliver("digest", "subject")

    assert ok is True
    assert message == "emailed you"


def test_deliver_can_skip_straight_to_slack(monkeypatch) -> None:
    def email_should_not_run(content, subject):
        raise AssertionError("email was tried despite prefer_slack")

    monkeypatch.setattr("src.delivery.send_email", email_should_not_run)
    monkeypatch.setattr(
        "src.delivery.send_to_slack",
        lambda content, target="slack": (True, "sent to slack"),
    )

    ok, message = deliver("digest", "subject", prefer_slack=True)

    assert ok is True
    assert message == "sent to slack"


def test_deliver_falls_back_to_slack_when_email_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.delivery.send_email",
        lambda content, subject: (False, "no smtp password"),
    )
    monkeypatch.setattr(
        "src.delivery.send_to_slack",
        lambda content, target="slack": (True, "sent to slack"),
    )

    ok, message = deliver("digest", "subject")

    assert ok is True
    assert message == "sent to slack"


def test_a_domain_can_send_to_its_own_recipients() -> None:
    sent, sender = capture()

    ok, message = send_email(
        "digest", "subject", settings(), send=sender,
        recipients=["partner@fund.com", "analyst@fund.com"],
    )

    assert ok is True
    # Replaces the owner's address for this message rather than adding to it.
    assert sent[0]["To"] == "partner@fund.com, analyst@fund.com"
    assert "me@example.com" not in sent[0]["To"]
