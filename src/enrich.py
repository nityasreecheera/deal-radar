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

from src.models import FormDFiling
from src.normalize import normalize_company_name, normalize_domain


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_MAX_RESULTS = 5

# Sites that will never be a company's own homepage, so a hit here should not be
# mistaken for one. Directories rank well for company names, which is exactly
# the trap.
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
    """
    if not domain or domain in NON_COMPANY_DOMAINS:
        return False

    canonical = normalize_company_name(company_name)

    if not canonical:
        return False

    stem = domain.split(".")[0].replace("-", "")

    if not stem:
        return False

    return stem.startswith(canonical[:6]) or canonical.startswith(stem[:6])


def enrich_filing(
    filing: FormDFiling,
    search: SearchFunction | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
) -> Enrichment:
    """
    Look up what a company does.

    `confident` records whether a domain matching the company's own name was
    found. When it is False the description came from somewhere other than the
    company itself, and the judging step is told so rather than being handed a
    guess dressed as a fact.
    """
    searcher = search or create_tavily_search()

    payload = searcher(build_query(filing), max_results)
    results = payload.get("results") or []

    website: str | None = None
    domain: str | None = None
    description: str | None = None
    evidence: list[str] = []

    for item in results:
        url = str(item.get("url") or "").strip()

        if not url:
            continue

        evidence.append(url)

        candidate_domain = normalize_domain(url)

        if website is None and looks_like_own_site(
            candidate_domain, filing.company_name
        ):
            website = url
            domain = candidate_domain

            content = str(item.get("content") or "").strip()

            if content:
                description = content

    if description is None:
        # No homepage found. Fall back to the first substantive snippet, and
        # leave `confident` False so the judge knows the provenance is weaker.
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
