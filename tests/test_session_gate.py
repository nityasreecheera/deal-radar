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
