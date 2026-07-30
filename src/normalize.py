"""
Company-identity normalisation.

Copied from the sibling project investment-research-copilot rather than imported,
so the two repositories stay independent while both are still changing shape.
If a bug is fixed here, it needs fixing there too — that is the cost of the copy,
and it is cheaper than coupling.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse


COMPANY_SUFFIXES = {
    "ai",
    "inc",
    "incorporated",
    "labs",
    "limited",
    "llc",
    "ltd",
    "technologies",
    "technology",
    "corp",
    "corporation",
    "company",
    "co",
}

# Suffixes worth stripping on top of the sibling project's list, because SEC
# filings use legal entity names far more consistently than press coverage does.
LEGAL_SUFFIXES = {
    "lp",
    "llp",
    "plc",
    "pbc",
    "holdings",
    "group",
    "partners",
    "fund",
    "trust",
}

ALL_SUFFIXES = COMPANY_SUFFIXES | LEGAL_SUFFIXES


def normalize_domain(url: str | None) -> str | None:
    """
    Convert a URL into a canonical domain.

    Examples:
        https://www.example.com/about -> example.com
        example.com -> example.com
    """
    if not url:
        return None

    value = url.strip().lower()

    if not value:
        return None

    if "://" not in value:
        value = f"https://{value}"

    parsed = urlparse(value)
    domain = parsed.netloc or parsed.path.split("/")[0]

    domain = domain.lower().strip()
    domain = domain.split(":")[0]

    if domain.startswith("www."):
        domain = domain[4:]

    return domain or None


def normalize_company_name(name: str) -> str:
    """
    Normalise a company name for duplicate comparison.

    Trailing legal and generic suffixes are stripped repeatedly, so
    "Acme Health Technologies, Inc." and "Acme Health" collapse together.

    Examples:
        PreventiveMD, Inc. -> preventivemd
        Acme Health Technologies, Inc. -> acmehealth
    """
    value = name.lower().strip()
    value = value.replace("&", "and")

    words = re.findall(r"[a-z0-9]+", value)

    while words and words[-1] in ALL_SUFFIXES:
        words.pop()

    return "".join(words)


def slugify_company_name(name: str) -> str:
    """
    Convert a company name into a filesystem- and URL-safe slug.

    Unlike normalize_company_name this keeps word boundaries and suffixes, so it
    stays readable. It is for display and paths, never for identity comparison.

    Example:
        "PreventiveMD, Inc." -> "preventivemd-inc"
    """
    value = name.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")

    return value or "unknown-company"
