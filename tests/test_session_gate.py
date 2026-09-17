"""
The password gate, as exercised over HTTP against the running site.

These are integration checks rather than unit tests: the gate lives in Next's
proxy layer, and the thing worth proving is what an unauthenticated request
actually receives — not what a function returns.

Skipped unless the site is running locally, so the offline suite stays offline.
"""

import os

import httpx
import pytest


SITE = os.getenv("RADAR_SITE", "http://127.0.0.1:3100")


def site_is_up() -> bool:
    try:
        httpx.get(f"{SITE}/api/meta", timeout=2)
    except Exception:  # noqa: BLE001
        return False

    return True


pytestmark = pytest.mark.skipif(
    not site_is_up(), reason="the site is not running locally"
)


def test_the_api_refuses_without_credentials() -> None:
    # share.sh will not publish until this is true.
    response = httpx.get(f"{SITE}/api/meta", timeout=10)

    assert response.status_code == 401
    assert "Basic" in response.headers.get("www-authenticate", "")


def test_a_person_is_sent_to_the_login_form() -> None:
    response = httpx.get(f"{SITE}/", timeout=10, follow_redirects=False)

    assert response.status_code in (302, 303, 307)
    assert "/login" in response.headers["location"]


def test_the_login_page_is_reachable_without_a_session() -> None:
    # Otherwise there is no way to get one.
    assert httpx.get(f"{SITE}/login", timeout=10).status_code == 200


def test_basic_auth_still_works_for_scripts() -> None:
    user = os.getenv("SHARE_USER")
    password = os.getenv("SHARE_PASSWORD")

    if not user or not password:
        pytest.skip("no credentials in the environment")

    response = httpx.get(f"{SITE}/api/meta", auth=(user, password), timeout=10)

    assert response.status_code == 200


def test_signing_in_sets_a_session_and_signing_out_clears_it() -> None:
    user = os.getenv("SHARE_USER")
    password = os.getenv("SHARE_PASSWORD")

    if not user or not password:
        pytest.skip("no credentials in the environment")

    with httpx.Client(base_url=SITE, timeout=10, follow_redirects=False) as client:
        signed_in = client.post(
            "/auth/login", data={"password": password, "next": "/"}
        )

        assert signed_in.status_code == 303
        assert "radar_session" in signed_in.cookies

        # The cookie alone now gets you in, with no Authorization header.
        assert client.get("/api/meta").status_code == 200

        client.post("/auth/logout")

        # And out again.
        assert client.get("/", follow_redirects=False).status_code in (302, 303, 307)


def test_a_wrong_password_does_not_sign_you_in() -> None:
    with httpx.Client(base_url=SITE, timeout=10, follow_redirects=False) as client:
        response = client.post("/auth/login", data={"password": "not-the-password"})

        assert response.status_code == 303
        assert "error=1" in response.headers["location"]
        assert client.get("/api/meta").status_code == 401


# --- invite links -----------------------------------------------------------
#
# A link that grants access for a week and then stops. The thing worth proving
# is the "and then stops" half: an expiring credential that quietly does not
# expire is worse than a password, because nobody goes looking for it.

import base64
import hashlib
import hmac as hmac_module
import re
import time
from pathlib import Path


def share_password() -> str | None:
    env = Path(__file__).resolve().parent.parent / "web" / ".env.local"

    if not env.exists():
        return None

    found = re.search(r"^SHARE_PASSWORD\s*=\s*(.+)$", env.read_text(), re.M)

    return found.group(1).strip().strip("\"'") if found else None


def invite_token(expires_at_ms: int, secret: str) -> str:
    payload = f"invite:{expires_at_ms}"
    digest = hmac_module.new(
        secret.encode(), payload.encode(), hashlib.sha256
    ).digest()
    signature = base64.urlsafe_b64encode(digest).decode().rstrip("=")

    return f"{payload}.{signature}"


needs_password = pytest.mark.skipif(
    share_password() is None, reason="no share password configured"
)


@needs_password
def test_a_valid_invite_grants_a_session() -> None:
    week = int(time.time() * 1000) + 7 * 24 * 60 * 60 * 1000
    token = invite_token(week, share_password())

    response = httpx.get(
        f"{SITE}/invite", params={"t": token}, timeout=10, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert "radar_session" in response.cookies


@needs_password
def test_an_expired_invite_grants_nothing() -> None:
    yesterday = int(time.time() * 1000) - 24 * 60 * 60 * 1000
    token = invite_token(yesterday, share_password())

    response = httpx.get(
        f"{SITE}/invite", params={"t": token}, timeout=10, follow_redirects=False
    )

    assert "radar_session" not in response.cookies
    assert "/login" in response.headers["location"]


@needs_password
def test_the_expiry_cannot_be_edited_by_whoever_holds_the_link() -> None:
    """
    The date is inside the signed payload. Moving it forward invalidates the
    signature rather than extending the link.
    """
    yesterday = int(time.time() * 1000) - 24 * 60 * 60 * 1000
    far_off = int(time.time() * 1000) + 365 * 24 * 60 * 60 * 1000

    tampered = invite_token(yesterday, share_password()).replace(
        str(yesterday), str(far_off)
    )

    response = httpx.get(
        f"{SITE}/invite", params={"t": tampered}, timeout=10, follow_redirects=False
    )

    assert "radar_session" not in response.cookies


def test_an_unsigned_invite_grants_nothing() -> None:
    far_off = int(time.time() * 1000) + 365 * 24 * 60 * 60 * 1000

    response = httpx.get(
        f"{SITE}/invite",
        params={"t": invite_token(far_off, "not-the-password")},
        timeout=10,
        follow_redirects=False,
    )

    assert "radar_session" not in response.cookies


def test_the_invite_path_does_not_open_the_site() -> None:
    """Reachable without a session, but it hands out nothing on its own."""
    response = httpx.get(f"{SITE}/invite", timeout=10, follow_redirects=False)

    assert "radar_session" not in response.cookies
    assert "/login" in response.headers["location"]


# --- named guests -----------------------------------------------------------
#
# A guest signs in with a name and no password. What makes that safe to hand to
# a stranger is not the name — it is guessable by design — but everything
# around it: the session expires on its own, and it cannot write.

GUEST_NAME = os.getenv("RADAR_GUEST", "leonisguest")


def guest_session() -> httpx.Client | None:
    """
    Sign in as the guest, or None if no guest is configured on this site.

    Returns the client already signed in and already open — callers use it
    directly rather than in a `with`, because entering a client that has served
    a request raises.
    """
    client = httpx.Client(base_url=SITE, timeout=10, follow_redirects=False)
    client.post("/auth/login", data={"user": GUEST_NAME, "password": ""})

    if "radar_session" not in client.cookies:
        client.close()
        return None

    return client


def guest_is_configured() -> bool:
    client = guest_session()

    if client is None:
        return False

    client.close()

    return True


needs_guest = pytest.mark.skipif(
    not guest_is_configured(), reason="no guest configured on this site"
)


@needs_guest
def test_a_guest_name_alone_signs_in() -> None:
    client = guest_session()

    try:
        assert client.get("/api/meta").status_code == 200
    finally:
        client.close()


@needs_guest
def test_a_guest_cannot_write() -> None:
    """
    The point of the read-only rule: a visitor must not be able to overwrite
    judgements, or clear the unread marks, on someone else's radar.
    """
    client = guest_session()

    try:
        assert client.post("/api/viewed").status_code == 403
    finally:
        client.close()


@needs_guest
def test_a_guest_cannot_spend_money() -> None:
    """/api/chat calls a paid model on every request."""
    client = guest_session()

    try:
        response = client.post("/api/chat", json={"question": "anything"})

        assert response.status_code == 403
    finally:
        client.close()


@needs_guest
def test_a_guest_session_carries_its_own_expiry() -> None:
    """
    Not the usual fortnight. The cookie must die on the guest's date, so access
    lapses without anyone remembering to remove it.
    """
    client = guest_session()

    try:
        cookie = next(c for c in client.cookies.jar if c.name == "radar_session")

        assert cookie.expires is not None
        assert cookie.expires < time.time() + 15 * 24 * 60 * 60
    finally:
        client.close()


def test_an_unknown_guest_name_does_not_sign_in() -> None:
    client = httpx.Client(base_url=SITE, timeout=10, follow_redirects=False)

    try:
        client.post("/auth/login", data={"user": "nosuchguest", "password": ""})

        assert "radar_session" not in client.cookies
    finally:
        client.close()
