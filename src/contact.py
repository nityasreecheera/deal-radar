"""
Finding a company's own contact address on its own website.

Deliberately conservative. A page is full of things that look like email
addresses and are not — `bootstrap@4.1.3` and `core-js-bundle@3.2.1` are npm
package versions, `wght@300..700` is CSS, and `support@webador.com` belongs to
whoever built the site rather than the company that filed.

One rule removes almost all of it: keep an address only if its domain matches the
company's own website. Measured against twenty real sites, a naive scan looked
like a 70% hit rate and was really 40% once the junk was removed. A contact list
that is half wrong is worse than a short one that is right.

Nothing here decides anything or spends money on a model. It fetches a page a
company publishes publicly and reads what is on it.
"""

from __future__ import annotations

import re
from typing import Callable
from urllib.parse import urlparse

import httpx


USER_AGENT = "deal-radar research (nityasree.cheera24@gmail.com)"

# Pages worth trying, in order. Most companies put an address on the homepage or
# one click away; anything deeper is usually a careers portal.
CONTACT_PATHS = ("", "/contact", "/contact-us", "/about")

EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]{2,}")

# Local parts that mean "a person put this here for people to use".
PREFERRED_PREFIXES = (
    "hello",
    "contact",
    "info",
    "team",
    "hi",
    "founders",
    "invest",
    "ir",
)

# Never worth keeping even when the domain matches.
UNWANTED_PREFIXES = ("noreply", "no-reply", "donotreply", "postmaster", "abuse")

MAX_BYTES = 400_000


def registrable_domain(url_or_email: str) -> str:
    """
    The part of a domain worth comparing.

    Strips scheme, `www.` and any subdomain beyond the last two labels, so
    `https://www.acme.co.uk/contact` and `hello@mail.acme.co.uk` both reduce to
    something comparable. Not a public-suffix implementation — a two-label
    comparison is enough to tell a company's own address from its website
    builder's, and pulling in a suffix list for that would be overkill.
    """
    text = url_or_email.strip().lower()

    if "@" in text:
        host = text.rsplit("@", 1)[1]
    else:
        if "//" not in text:
            text = "https://" + text
        host = urlparse(text).netloc or ""

    host = host.split(":")[0].removeprefix("www.")
    labels = [label for label in host.split(".") if label]

    if len(labels) <= 2:
        return ".".join(labels)

    # co.uk, com.au and friends: keep three labels when the second-to-last is a
    # known second-level suffix.
    if labels[-2] in ("co", "com", "org", "net", "ac", "gov") and len(labels[-1]) == 2:
        return ".".join(labels[-3:])

    return ".".join(labels[-2:])


def looks_like_an_address(text: str) -> bool:
    """
    Whether a match is plausibly an email rather than a version string.

    `bootstrap@4.1.3` matches the pattern perfectly well. What it does not have
    is a domain whose last label is alphabetic.
    """
    if "@" not in text:
        return False

    domain = text.rsplit("@", 1)[1].rstrip(".")
    labels = domain.split(".")

    if len(labels) < 2:
        return False

    # A numeric or one-character final label is a version number, not a TLD.
    return labels[-1].isalpha() and len(labels[-1]) >= 2


def extract_addresses(page: str, website: str) -> list[str]:
    """
    Every address on a page that belongs to the company whose page it is.

    Ordered so a general inbox comes first: `hello@` is meant to be written to,
    a named individual's address on a public page usually is too but is a
    stronger thing to use, and neither should be buried behind a careers alias.
    """
    site_domain = registrable_domain(website)

    if not site_domain:
        return []

    found: list[str] = []

    for raw in EMAIL_PATTERN.findall(page):
        address = raw.strip().rstrip(".").lower()

        if not looks_like_an_address(address):
            continue

        local = address.split("@", 1)[0]

        if local.startswith(UNWANTED_PREFIXES):
            continue

        # The rule that does the work. Without it you collect the site builder,
        # the PR agency and every npm dependency.
        if registrable_domain(address) != site_domain:
            continue

        if address not in found:
            found.append(address)

    def rank(address: str) -> tuple[int, int]:
        local = address.split("@", 1)[0]
        preferred = local in PREFERRED_PREFIXES

        return (0 if preferred else 1, len(address))

    return sorted(found, key=rank)


def find_contact_email(
    website: str | None,
    fetch: Callable[[str], str] | None = None,
) -> str | None:
    """
    The best contact address for a company, or None.

    Stops at the first page that yields anything, so a company with an address
    on its homepage costs one request rather than four.
    """
    if not website:
        return None

    fetcher = fetch or create_page_fetcher()
    base = website.rstrip("/")

    for path in CONTACT_PATHS:
        try:
            page = fetcher(base + path)
        except Exception:  # noqa: BLE001 - an unreachable page is not an error
            continue

        addresses = extract_addresses(page, base)

        if addresses:
            return addresses[0]

    return None


def create_page_fetcher() -> Callable[[str], str]:
    """Fetch a public page, identifying who is asking."""
    client = httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=12.0,
        follow_redirects=True,
    )

    def fetch(url: str) -> str:
        response = client.get(url)
        response.raise_for_status()

        return response.text[:MAX_BYTES]

    return fetch


def gmail_compose_url(
    address: str,
    subject: str = "",
    body: str = "",
) -> str:
    """
    A link that opens Gmail's compose window with the fields filled in.

    Gmail rather than a `mailto:` because a mailto opens whatever desktop client
    the machine happens to think it has, which on most laptops is nothing useful.
    """
    from urllib.parse import quote

    parts = [f"to={quote(address)}"]

    if subject:
        parts.append(f"su={quote(subject)}")

    if body:
        parts.append(f"body={quote(body)}")

    return "https://mail.google.com/mail/?view=cm&fs=1&" + "&".join(parts)


def gmail_search_url(query: str) -> str:
    """
    A link that opens Gmail searching for correspondence with a company.

    This is the cheap answer to "did I already email them, and what did they
    say". It reads nothing and stores nothing — it just points the browser at a
    search the analyst could have typed. Actually syncing threads means the
    Gmail API and an OAuth flow, which is a much larger thing to own.
    """
    from urllib.parse import quote

    return f"https://mail.google.com/mail/u/0/#search/{quote(query)}"
