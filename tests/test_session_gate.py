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


# --- guest access, removed -------------------------------------------------
#
# Guests used to sign in with a name alone and got a cookie marked ":guest".
# That access is gone, and a cookie minted before it went must not be read as
# the owner's just because its marker is no longer recognised.

def guest_cookie(expires_at_ms: int, secret: str) -> str:
    payload = f"{int(time.time() * 1000)}:{expires_at_ms}:guest"
    digest = hmac_module.new(secret.encode(), payload.encode(), hashlib.sha256).digest()

    return f"{payload}.{base64.urlsafe_b64encode(digest).decode().rstrip('=')}"


@needs_password
def test_an_old_guest_cookie_grants_nothing() -> None:
    week = int(time.time() * 1000) + 7 * 24 * 60 * 60 * 1000
    cookie = guest_cookie(week, share_password())

    response = httpx.get(
        f"{SITE}/api/candidates?limit=1",
        cookies={"radar_session": cookie},
        timeout=10,
    )

    assert response.status_code == 401


def test_a_name_without_a_password_does_not_sign_in() -> None:
    client = httpx.Client(base_url=SITE, timeout=10, follow_redirects=False)

    try:
        client.post("/auth/login", data={"user": "leonisguest", "password": ""})

        assert "radar_session" not in client.cookies
    finally:
        client.close()


# --- API tokens -------------------------------------------------------------
#
# For someone else's program. A token lives in a loop somebody else controls,
# so what it cannot do matters more than what it can.

def api_token(name: str, scope: str, expires_at_ms: int, secret: str) -> str:
    payload = f"token:{name}:{scope}:{expires_at_ms}"
    digest = hmac_module.new(secret.encode(), payload.encode(), hashlib.sha256).digest()

    return f"{payload}.{base64.urlsafe_b64encode(digest).decode().rstrip('=')}"


def bearer(scope: str, days: int = 30, name: str = "friend") -> dict[str, str]:
    expires = int(time.time() * 1000) + days * 24 * 60 * 60 * 1000

    return {"Authorization": f"Bearer {api_token(name, scope, expires, share_password())}"}


@needs_password
def test_a_read_token_reads() -> None:
    response = httpx.get(f"{SITE}/api/candidates?limit=1", headers=bearer("read"), timeout=10)

    assert response.status_code == 200


@needs_password
def test_a_read_token_cannot_write() -> None:
    response = httpx.post(f"{SITE}/api/viewed", headers=bearer("read"), timeout=10)

    assert response.status_code == 403


@needs_password
def test_a_read_token_cannot_spend_money() -> None:
    """A token sits inside a loop somebody else wrote. /api/chat bills per call."""
    response = httpx.post(
        f"{SITE}/api/chat", headers=bearer("read"), json={"question": "hi"}, timeout=10
    )

    assert response.status_code == 403


@needs_password
def test_an_old_sandbox_token_grants_nothing() -> None:
    """The sandbox scope is gone, so a correctly signed one is now just invalid."""
    response = httpx.get(
        f"{SITE}/api/candidates?limit=1", headers=bearer("sandbox"), timeout=10
    )

    assert response.status_code == 401


@needs_password
def test_an_expired_token_grants_nothing() -> None:
    response = httpx.get(
        f"{SITE}/api/candidates?limit=1", headers=bearer("read", days=-1), timeout=10
    )

    assert response.status_code == 401


@needs_password
def test_the_token_cannot_be_edited_by_whoever_holds_it() -> None:
    """The name is inside the signature, so renaming the token breaks it."""
    header = bearer("read", name="friend")
    tampered = header["Authorization"].replace(":friend:", ":someone:")

    response = httpx.get(
        f"{SITE}/api/candidates?limit=1",
        headers={"Authorization": tampered},
        timeout=10,
    )

    assert response.status_code == 401


def test_an_unsigned_token_grants_nothing() -> None:
    expires = int(time.time() * 1000) + 86_400_000
    token = api_token("friend", "read", expires, "not-the-password")

    response = httpx.get(
        f"{SITE}/api/candidates?limit=1",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )

    assert response.status_code == 401
