"""
Enrichment: work out what a company actually does.

A Form D says who raised money and how much. It does not say what the company
builds, and it never carries a website. Everything downstream needs that, so
this is the step that turns a filing into something judgeable.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field

from src.contact import registrable_domain
from src.models import FormDFiling
from src.normalize import normalize_company_name, normalize_domain


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_MAX_RESULTS = 5

# Sites that will never be a company's own homepage, so a hit here should not be
# mistaken for one. Directories rank well for company names, which is exactly
# the trap.
# Never a company's own site, whatever the name suggests.
INSTITUTIONAL_SUFFIXES = (".edu", ".ac.uk", ".gov", ".mil", ".edu.au", ".ac.in")

NON_COMPANY_DOMAINS = {
    "bloomberg.com",
    "crunchbase.com",
    "dnb.com",
    "facebook.com",
    "glassdoor.com",
    "instagram.com",
    "linkedin.com",
    "pitchbook.com",
    "sec.gov",
    "tracxn.com",
    "twitter.com",
    "x.com",
    "zoominfo.com",
}

# Pages that live on a company's own domain but describe nothing about the
# business. Search engines return these constantly, and a terms-of-use page as
# evidence produces a shrug from the judging step rather than a verdict.
BOILERPLATE_PATH_MARKERS = (
    "privacy",
    "terms",
    "legal",
    "cookie",
    "disclaimer",
    "accessibility",
    "team",
    "leadership",
    "careers",
    "jobs",
    "contact",
    "login",
    "signin",
    "sign-in",
    "press",
    "blog",
)

SearchFunction = Callable[[str, int], dict[str, Any]]


class EnrichmentError(RuntimeError):
    """Raised when the search backend cannot be constructed."""


class Enrichment(BaseModel):
    """What could be established about a company beyond its filing."""

    website: str | None = None
    canonical_domain: str | None = None
    description: str | None = None
    evidence_urls: list[str] = Field(default_factory=list)
    confident: bool = False


def create_tavily_search() -> SearchFunction:
    """Build a search function backed by Tavily."""
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")

    api_key = os.getenv("TAVILY_API_KEY")

    if not api_key:
        raise EnrichmentError(
            "TAVILY_API_KEY is not set. Copy .env.example to .env and add a "
            "key from https://app.tavily.com"
        )

    try:
        from tavily import TavilyClient
    except ImportError as exc:
        raise EnrichmentError(
            "tavily-python is not installed. Run: pip install -r requirements.txt"
        ) from exc

    client = TavilyClient(api_key=api_key)

    def search(query: str, max_results: int) -> dict[str, Any]:
        return client.search(query=query, max_results=max_results)

    return search


def build_query(filing: FormDFiling) -> str:
    """
    Build a search query for one filing.

    The city is included because company names in this sector are generic
    enough to collide — several unrelated companies are called some variation
    of "Health AI".
    """
    parts = [filing.company_name]

    if filing.city:
        parts.append(filing.city.title())

    return " ".join(parts)


def looks_like_own_site(domain: str | None, company_name: str) -> bool:
    """
    Whether a domain plausibly belongs to this company.

    Compares the domain against the normalised company name rather than trying
    to be clever: if the name's letters appear in the domain, it is very likely
    theirs, and if not, we say so instead of guessing.

    The comparison is against the registrable domain, not the leftmost label.
    A subdomain will happily match a company name that has nothing to do with
    it: "Mae Labs, Inc." was given www.mae.ucla.edu, UCLA's Mechanical and
    Aerospace Engineering department, because "mae" is the start of "maelabs".
    Against "ucla" it fails, which is the right answer.
    """
    if not domain or domain in NON_COMPANY_DOMAINS:
        return False

    # Institutions are not startups. A university department, a government
    # office or a military site is never a company's own homepage, however
    # neatly its acronym lines up with the name on a filing.
    if any(domain.endswith(suffix) for suffix in INSTITUTIONAL_SUFFIXES):
        return False

    canonical = normalize_company_name(company_name)

    if not canonical:
        return False

    registrable = registrable_domain(domain)

    if registrable in NON_COMPANY_DOMAINS:
        return False

    stem = registrable.split(".")[0].replace("-", "")

    if not stem:
        return False

    return stem.startswith(canonical[:6]) or canonical.startswith(stem[:6])


def page_depth(url: str) -> int:
    """How many path segments a URL has. A homepage has none."""
    path = url.split("://", 1)[-1]
    segments = [part for part in path.split("/")[1:] if part]

    return len(segments)


def is_boilerplate(url: str) -> bool:
    """Whether a URL looks like a page that describes no product."""
    lowered = url.lower()

    return any(marker in lowered for marker in BOILERPLATE_PATH_MARKERS)


def rank_own_pages(
    results: list[dict[str, Any]],
    company_name: str,
) -> list[dict[str, Any]]:
    """
    Order a company's own pages by how likely they are to describe the business.

    Search returns whichever page matched, which is very often a terms-of-use or
    team page. Those sit on the right domain and say nothing, so preferring the
    shallowest non-boilerplate URL matters more than it sounds: the difference is
    between a verdict and a shrug.
    """
    own = [
        item
        for item in results
        if looks_like_own_site(
            normalize_domain(str(item.get("url") or "")), company_name
        )
    ]

    return sorted(
        own,
        key=lambda item: (
            is_boilerplate(str(item.get("url") or "")),
            page_depth(str(item.get("url") or "")),
            not str(item.get("content") or "").strip(),
        ),
    )


def enrich_filing(
    filing: FormDFiling,
    search: SearchFunction | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
) -> Enrichment:
    """
    Look up what a company does.

    `confident` records whether a page on the company's own domain was found.
    When it is False the description came from somewhere else, and the judging
    step is told so rather than being handed a guess dressed as a fact.
    """
    searcher = search or create_tavily_search()

    payload = searcher(build_query(filing), max_results)
    results = payload.get("results") or []

    evidence = [
        str(item.get("url") or "").strip()
        for item in results
        if str(item.get("url") or "").strip()
    ]

    own_pages = rank_own_pages(results, filing.company_name)

    website: str | None = None
    domain: str | None = None
    description: str | None = None

    if own_pages:
        best = own_pages[0]
        website = str(best.get("url"))
        domain = normalize_domain(website)

        # Take the description from the best-ranked own page that actually has
        # content, which may not be the best-ranked page overall.
        for item in own_pages:
            content = str(item.get("content") or "").strip()

            if content:
                description = content
                break

    if description is None:
        # Nothing on their own domain said anything. Fall back to any snippet and
        # leave `confident` reflecting that provenance is weaker.
        for item in results:
            content = str(item.get("content") or "").strip()

            if content:
                description = content
                break

    return Enrichment(
        website=website,
        canonical_domain=domain,
        description=description,
        evidence_urls=evidence[:max_results],
        confident=website is not None,
    )


if __name__ == "__main__":
    example = FormDFiling(
        accession="0002147093-26-000001",
        cik="0002147093",
        company_name="PreventiveMD, Inc.",
        filed_date="2026-07-27",
        industry_group="Other Health Care",
        city="RALEIGH",
        state="NC",
    )

    result = enrich_filing(example)

    print("website:", result.website)
    print("confident:", result.confident)
    print("description:", (result.description or "")[:200])
