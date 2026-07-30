from typing import Any

from src.enrich import (
    build_query,
    enrich_filing,
    looks_like_own_site,
)
from src.models import FormDFiling


def filing(**overrides) -> FormDFiling:
    data = {
        "accession": "acc-1",
        "cik": "1",
        "company_name": "PreventiveMD, Inc.",
        "filed_date": "2026-07-27",
        "industry_group": "Other Health Care",
        "city": "RALEIGH",
        "state": "NC",
    }
    data.update(overrides)

    return FormDFiling(**data)


def stub(results: list[dict[str, Any]]):
    def search(query: str, max_results: int) -> dict[str, Any]:
        return {"results": results}

    return search


def test_query_includes_the_city_to_disambiguate() -> None:
    # Names in this sector collide constantly, so location narrows it.
    assert build_query(filing()) == "PreventiveMD, Inc. Raleigh"


def test_query_without_a_city() -> None:
    assert build_query(filing(city=None)) == "PreventiveMD, Inc."


def test_own_site_recognised_from_the_name() -> None:
    assert looks_like_own_site("preventivemd.com", "PreventiveMD, Inc.") is True
    assert looks_like_own_site("preventive-md.io", "PreventiveMD, Inc.") is True


def test_directories_are_never_the_company_site() -> None:
    # These rank well for company names, which is exactly the trap.
    for domain in ("linkedin.com", "crunchbase.com", "sec.gov", "pitchbook.com"):
        assert looks_like_own_site(domain, "PreventiveMD, Inc.") is False


def test_an_unrelated_domain_is_not_the_company_site() -> None:
    assert looks_like_own_site("healthnews.com", "PreventiveMD, Inc.") is False


def test_no_domain_is_not_the_company_site() -> None:
    assert looks_like_own_site(None, "PreventiveMD, Inc.") is False


def test_enrichment_from_the_company_homepage_is_confident() -> None:
    result = enrich_filing(
        filing(),
        search=stub(
            [
                {
                    "url": "https://www.linkedin.com/company/preventivemd",
                    "content": "PreventiveMD | LinkedIn",
                },
                {
                    "url": "https://preventivemd.com",
                    "content": "Preventive care software for primary care.",
                },
            ]
        ),
    )

    assert result.confident is True
    assert result.website == "https://preventivemd.com"
    assert result.canonical_domain == "preventivemd.com"
    assert result.description == "Preventive care software for primary care."
    assert len(result.evidence_urls) == 2


def test_enrichment_without_a_homepage_is_not_confident() -> None:
    result = enrich_filing(
        filing(),
        search=stub(
            [
                {
                    "url": "https://healthnews.com/article",
                    "content": "A new health startup raised money.",
                }
            ]
        ),
    )

    assert result.confident is False
    assert result.website is None
    # The snippet is still kept — the judge is told its provenance is weak.
    assert result.description == "A new health startup raised money."


def test_enrichment_with_no_results_at_all() -> None:
    result = enrich_filing(filing(), search=stub([]))

    assert result.confident is False
    assert result.website is None
    assert result.description is None
    assert result.evidence_urls == []


def test_enrichment_skips_results_with_no_url() -> None:
    result = enrich_filing(
        filing(),
        search=stub([{"content": "no url here"}, {"url": "   "}]),
    )

    assert result.evidence_urls == []


def test_enrichment_prefers_the_homepage_over_an_earlier_snippet() -> None:
    result = enrich_filing(
        filing(),
        search=stub(
            [
                {"url": "https://news.example.com/x", "content": "News summary."},
                {"url": "https://preventivemd.com", "content": "Our platform."},
            ]
        ),
    )

    assert result.description == "Our platform."
    assert result.confident is True


def test_enrichment_tolerates_a_payload_without_results() -> None:
    def empty(query: str, max_results: int) -> dict[str, Any]:
        return {}

    result = enrich_filing(filing(), search=empty)

    assert result.confident is False
