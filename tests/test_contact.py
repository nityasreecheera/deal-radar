"""
Finding a company's own address, and nothing else.

Every case here came from a real website. The junk especially: a naive scan of
twenty sites looked like a 70% hit rate and was really 40%.
"""

from src.contact import (
    extract_addresses,
    find_contact_email,
    gmail_compose_url,
    gmail_search_url,
    looks_like_an_address,
    registrable_domain,
)


def test_a_version_string_is_not_an_email() -> None:
    # All real, all found on companies' own pages.
    assert looks_like_an_address("bootstrap@4.1.3") is False
    assert looks_like_an_address("core-js-bundle@3.2.1") is False
    assert looks_like_an_address("focus-within-polyfill@5.0.9") is False
    assert looks_like_an_address("tailwindcss-intersect@2.x.x") is False
    assert looks_like_an_address("wght@300..700") is False

    assert looks_like_an_address("hello@violet.ai") is True


def test_domains_reduce_to_something_comparable() -> None:
    assert registrable_domain("https://www.echovane.com/contact") == "echovane.com"
    assert registrable_domain("contact@echovane.com") == "echovane.com"
    assert registrable_domain("hello@mail.echovane.com") == "echovane.com"
    assert registrable_domain("https://echoesofemberltd.co.uk") == (
        "echoesofemberltd.co.uk"
    )


def test_only_the_companys_own_domain_survives() -> None:
    page = """
      <a href="mailto:contact@echovane.com">write to us</a>
      built with <a href="mailto:support@webador.com">webador</a>
      press: mmoyer@lifesciadvisors.com
      <script src="core-js-bundle@3.2.1"></script>
    """

    assert extract_addresses(page, "https://echovane.com") == [
        "contact@echovane.com"
    ]


def test_a_general_inbox_is_preferred_over_a_person() -> None:
    page = "astrid@kikitora.com and hello@kikitora.com"

    found = extract_addresses(page, "https://kikitora.com")

    # Both kept — a named person on a public page is worth having — but the
    # inbox meant for strangers comes first.
    assert found == ["hello@kikitora.com", "astrid@kikitora.com"]


def test_noreply_is_never_worth_keeping() -> None:
    page = "noreply@acme.com donotreply@acme.com hello@acme.com"

    assert extract_addresses(page, "https://acme.com") == ["hello@acme.com"]


def test_a_trailing_full_stop_is_not_part_of_the_address() -> None:
    # Real: "write to info@noosphere.app." at the end of a sentence.
    page = "Get in touch at info@noosphere.app."

    assert extract_addresses(page, "https://noosphere.app") == [
        "info@noosphere.app"
    ]


def test_the_first_page_that_answers_wins() -> None:
    asked: list[str] = []

    def fetch(url: str) -> str:
        asked.append(url)

        if url.endswith("/contact"):
            return "hello@acme.com"

        return "nothing here"

    assert find_contact_email("https://acme.com", fetch=fetch) == "hello@acme.com"
    # Homepage, then /contact. It stops rather than trying every path.
    assert asked == ["https://acme.com", "https://acme.com/contact"]


def test_an_unreachable_page_is_not_a_crash() -> None:
    def fetch(url: str) -> str:
        raise RuntimeError("connection refused")

    assert find_contact_email("https://acme.com", fetch=fetch) is None


def test_no_website_means_no_lookup() -> None:
    def fetch(url: str) -> str:  # pragma: no cover - must never be called
        raise AssertionError("should not fetch without a website")

    assert find_contact_email(None, fetch=fetch) is None
    assert find_contact_email("", fetch=fetch) is None


def test_the_compose_link_fills_the_fields_in() -> None:
    url = gmail_compose_url("hello@acme.com", subject="Your Form D")

    assert "to=hello%40acme.com" in url
    assert "su=Your%20Form%20D" in url
    assert url.startswith("https://mail.google.com/mail/?view=cm")


def test_the_search_link_points_at_gmail() -> None:
    assert gmail_search_url("acme.com").endswith("acme.com")
