from typing import Any

from src.enrich import (
    build_query,
    enrich_filing,
    is_boilerplate,
    looks_like_own_site,
    page_depth,
    rank_own_pages,
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


def test_page_depth_counts_path_segments() -> None:
    assert page_depth("https://example.com") == 0
    assert page_depth("https://example.com/") == 0
    assert page_depth("https://example.com/about") == 1
    assert page_depth("https://example.com/legal/terms-of-use") == 2


def test_boilerplate_pages_are_recognised() -> None:
    # Every one of these was returned as a real company's "site" in a live run.
    assert is_boilerplate("https://preventivemd.com/terms-of-use") is True
    assert is_boilerplate("https://qualifiedhealthai.com/privacy-policy") is True
    assert is_boilerplate("https://rxsavecard.com/our-leadership-team") is True
    assert is_boilerplate("https://example.com/careers/engineer") is True

    assert is_boilerplate("https://example.com") is False
    assert is_boilerplate("https://example.com/product") is False


def test_own_pages_rank_the_homepage_above_boilerplate() -> None:
    ranked = rank_own_pages(
        [
            {"url": "https://acmehealth.com/privacy-policy", "content": "Privacy."},
            {"url": "https://acmehealth.com", "content": "We do trials."},
            {"url": "https://acmehealth.com/about/team", "content": "Our team."},
        ],
        "Acme Health, Inc.",
    )

    # Only the first pick matters. Both other pages are boilerplate — /about/team
    # matches on "team" — so their relative order is irrelevant.
    assert ranked[0]["url"] == "https://acmehealth.com"
    assert len(ranked) == 3


def test_own_pages_prefer_shallower_paths() -> None:
    ranked = rank_own_pages(
        [
            {"url": "https://acmehealth.com/solutions/clinical/trials", "content": "x"},
            {"url": "https://acmehealth.com/product", "content": "y"},
        ],
        "Acme Health, Inc.",
    )

    assert ranked[0]["url"] == "https://acmehealth.com/product"


def test_own_pages_exclude_other_domains() -> None:
    ranked = rank_own_pages(
        [
            {"url": "https://linkedin.com/company/acmehealth", "content": "x"},
            {"url": "https://acmehealth.com", "content": "y"},
        ],
        "Acme Health, Inc.",
    )

    assert len(ranked) == 1
    assert ranked[0]["url"] == "https://acmehealth.com"


def test_enrichment_avoids_a_boilerplate_page_when_a_homepage_exists() -> None:
    # This is the live failure: search returned terms-of-use, which describes
    # nothing, and the judge could only answer "maybe".
    result = enrich_filing(
        filing(company_name="PreventiveMD, Inc."),
        search=stub(
            [
                {
                    "url": "https://www.preventivemd.com/terms-of-use",
                    "content": "These terms govern your use of the site.",
                },
                {
                    "url": "https://www.preventivemd.com",
                    "content": "Preventive care software for primary care clinics.",
                },
            ]
        ),
    )

    assert result.website == "https://www.preventivemd.com"
    assert result.description == "Preventive care software for primary care clinics."


def test_enrichment_still_uses_boilerplate_if_it_is_all_there_is() -> None:
    # Weak evidence beats none, and the judge is told the provenance.
    result = enrich_filing(
        filing(company_name="PreventiveMD, Inc."),
        search=stub(
            [
                {
                    "url": "https://www.preventivemd.com/terms-of-use",
                    "content": "These terms govern your use of the site.",
                }
            ]
        ),
    )

    assert result.website == "https://www.preventivemd.com/terms-of-use"
    assert result.confident is True


def test_enrichment_falls_back_to_a_deeper_own_page_that_has_content() -> None:
    # The best-ranked page may have no snippet at all.
    result = enrich_filing(
        filing(company_name="PreventiveMD, Inc."),
        search=stub(
            [
                {"url": "https://www.preventivemd.com", "content": ""},
                {
                    "url": "https://www.preventivemd.com/product",
                    "content": "Our platform screens patients.",
                },
            ]
        ),
    )

    assert result.website == "https://www.preventivemd.com"
    assert result.description == "Our platform screens patients."


def test_enrichment_tolerates_a_payload_without_results() -> None:
    def empty(query: str, max_results: int) -> dict[str, Any]:
        return {}

    result = enrich_filing(filing(), search=empty)

    assert result.confident is False


def test_a_subdomain_that_echoes_the_name_is_not_the_company() -> None:
    """
    "Mae Labs, Inc." was given www.mae.ucla.edu — UCLA's Mechanical and
    Aerospace Engineering department — because "mae" starts "maelabs". The
    description that came back described a university research centre, and it
    reached a reader as though it were the company.
    """
    assert not looks_like_own_site("mae.ucla.edu", "Mae Labs, Inc.")


def test_a_university_is_never_the_company() -> None:
    assert not looks_like_own_site("stanford.edu", "Stanford Robotics Inc.")
    assert not looks_like_own_site("energy.gov", "Energy Systems Inc.")


def test_a_real_match_still_passes() -> None:
    assert looks_like_own_site("glaciantech.com", "Glacian Technologies Inc.")
    assert looks_like_own_site("www.glaciantech.com", "Glacian Technologies Inc.")


def test_a_company_on_its_own_subdomain_still_passes() -> None:
    assert looks_like_own_site("about.glaciantech.com", "Glacian Technologies Inc.")
