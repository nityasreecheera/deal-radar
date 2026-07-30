import json
from pathlib import Path

import pytest

from src.edgar import (
    EdgarError,
    build_search_url,
    fetch_filings,
    filing_xml_url,
    parse_form_d,
    parse_search_results,
    total_hits,
)


FIXTURES = Path(__file__).parent / "fixtures"


def real_filing_xml() -> str:
    """A genuine Form D pulled from EDGAR, kept so tests run offline."""
    return (FIXTURES / "preventivemd_form_d.xml").read_text(encoding="utf-8")


def search_payload(
    accession: str = "0002147093-26-000001",
    cik: str = "0002147093",
    filed_date: str = "2026-07-27",
    total: int = 1,
) -> dict:
    return {
        "hits": {
            "total": {"value": total},
            "hits": [
                {
                    "_id": f"{accession}:primary_doc.xml",
                    "_source": {
                        "ciks": [cik],
                        "file_date": filed_date,
                        "display_names": [f"Example Inc.  (CIK {cik})"],
                    },
                }
            ],
        }
    }


def test_search_url_quotes_the_industry_phrase() -> None:
    url = build_search_url("Other Health Care", "2026-07-01", "2026-07-29")

    assert "forms=D" in url
    assert "startdt=2026-07-01" in url
    assert "enddt=2026-07-29" in url
    # The phrase must stay quoted or the search matches each word separately.
    assert "%22" in url


def test_search_url_adds_an_offset_only_when_paging() -> None:
    first = build_search_url("Biotechnology", "2026-07-01", "2026-07-29")
    second = build_search_url("Biotechnology", "2026-07-01", "2026-07-29", 10)

    assert "from=" not in first
    assert "from=10" in second


def test_filing_url_strips_cik_zeros_and_accession_dashes() -> None:
    url = filing_xml_url("0002147093", "0002147093-26-000001")

    assert url.endswith("/data/2147093/000214709326000001/primary_doc.xml")


def test_parse_search_results_extracts_identifiers() -> None:
    results = parse_search_results(search_payload())

    assert results == [
        {
            "accession": "0002147093-26-000001",
            "cik": "0002147093",
            "filed_date": "2026-07-27",
        }
    ]


def test_parse_search_results_skips_malformed_hits() -> None:
    payload = {
        "hits": {
            "total": {"value": 3},
            "hits": [
                {"_id": "no-colon", "_source": {"ciks": ["1"]}},
                {"_id": "a:primary_doc.xml", "_source": {"ciks": []}},
                {"_id": "b:primary_doc.xml", "_source": {"ciks": ["2"]}},
            ],
        }
    }

    assert [r["accession"] for r in parse_search_results(payload)] == ["b"]


def test_total_hits_defaults_to_zero() -> None:
    assert total_hits({}) == 0
    assert total_hits(search_payload(total=82)) == 82


def test_parse_real_filing() -> None:
    filing = parse_form_d(
        real_filing_xml(),
        "0002147093-26-000001",
        "2026-07-27",
    )

    assert filing.company_name == "PreventiveMD, Inc."
    assert filing.cik == "0002147093"
    assert filing.industry_group == "Other Health Care"
    assert filing.in_groups(['Other Health Care']) is True
    assert filing.entity_type == "Corporation"
    assert filing.jurisdiction == "DELAWARE"
    assert filing.year_of_incorporation == 2026
    assert filing.city == "RALEIGH"
    assert filing.state == "NC"
    assert filing.total_offering_amount == 2000000
    assert filing.total_amount_sold == 1699999
    assert filing.investor_count == 2
    assert filing.is_amendment is False


def test_parse_real_filing_reads_related_people() -> None:
    filing = parse_form_d(
        real_filing_xml(),
        "0002147093-26-000001",
        "2026-07-27",
    )

    names = [person.full_name for person in filing.related_persons]

    assert "Brian Conyer" in names
    assert "Drew Glover" in names

    founder = next(p for p in filing.related_persons if p.last_name == "Conyer")

    assert "Executive Officer" in founder.relationships
    assert founder.city == "RALEIGH"

    # A director based somewhere other than the company is often the investor's
    # board seat, which is why the address is worth keeping.
    director = next(p for p in filing.related_persons if p.last_name == "Glover")

    assert director.relationships == ["Director"]
    assert director.city == "San Francisco"


def test_identity_helpers_on_a_real_filing() -> None:
    filing = parse_form_d(real_filing_xml(), "acc", "2026-07-27")

    assert filing.canonical_name == "preventivemd"
    assert filing.slug == "preventivemd-inc"
    # Incorporated 2026 and filing in 2026 — the earliest possible stage.
    assert filing.is_newly_incorporated is True


def test_parse_survives_an_empty_offering_block() -> None:
    # An Element with no children is falsey, so a truthiness check here would
    # treat this <offeringData/> as absent. Regression guard.
    xml = (
        "<edgarSubmission>"
        "<primaryIssuer><cik>1</cik><entityName>Empty Co</entityName>"
        "<issuerAddress/></primaryIssuer>"
        "<offeringData/>"
        "</edgarSubmission>"
    )

    filing = parse_form_d(xml, "acc", "2026-07-27")

    assert filing.company_name == "Empty Co"
    assert filing.industry_group == "Unknown"
    assert filing.in_groups(['Other Health Care']) is False
    assert filing.total_offering_amount is None
    assert filing.city is None


def test_parse_reads_amounts_when_the_issuer_block_has_no_children() -> None:
    # The same trap on the address: present but empty.
    xml = (
        "<edgarSubmission>"
        "<primaryIssuer><cik>1</cik><entityName>Terse Co</entityName>"
        "<issuerAddress><city>Boston</city></issuerAddress></primaryIssuer>"
        "<offeringData>"
        "<industryGroup><industryGroupType>Biotechnology</industryGroupType>"
        "</industryGroup>"
        "<offeringSalesAmounts><totalOfferingAmount>500000"
        "</totalOfferingAmount></offeringSalesAmounts>"
        "</offeringData>"
        "</edgarSubmission>"
    )

    filing = parse_form_d(xml, "acc", "2026-07-27")

    assert filing.city == "Boston"
    assert filing.industry_group == "Biotechnology"
    assert filing.in_groups(["Biotechnology"]) is True
    assert filing.in_groups(["Other Health Care"]) is False
    assert filing.total_offering_amount == 500000
    assert filing.total_amount_sold is None


def test_parse_rejects_unparseable_xml() -> None:
    with pytest.raises(EdgarError, match="could not parse"):
        parse_form_d("<not closed", "acc", "2026-07-27")


def test_parse_rejects_a_filing_without_an_issuer() -> None:
    with pytest.raises(EdgarError, match="no primaryIssuer"):
        parse_form_d("<edgarSubmission></edgarSubmission>", "acc", "2026-07-27")


def test_parse_rejects_an_issuer_without_a_name() -> None:
    xml = "<edgarSubmission><primaryIssuer><cik>1</cik></primaryIssuer></edgarSubmission>"

    with pytest.raises(EdgarError, match="no issuer name or CIK"):
        parse_form_d(xml, "acc", "2026-07-27")


def test_fetch_healthcare_filings_end_to_end_offline() -> None:
    calls: list[str] = []

    def fake_fetch(url: str) -> str:
        calls.append(url)

        if url.startswith("https://efts.sec.gov"):
            # Only the first industry group returns anything.
            if "Other+Health+Care" in url:
                return json.dumps(search_payload())

            return json.dumps({"hits": {"total": {"value": 0}, "hits": []}})

        return real_filing_xml()

    filings, problems = fetch_filings(
        "2026-07-01",
        "2026-07-29",
        fetch=fake_fetch,
    )

    assert problems == []
    assert len(filings) == 1
    assert filings[0].company_name == "PreventiveMD, Inc."
    # One search per industry group, plus one document fetch.
    assert sum(1 for c in calls if "efts.sec.gov" in c) == 5


def test_fetch_records_a_problem_without_losing_the_batch() -> None:
    def fake_fetch(url: str) -> str:
        if url.startswith("https://efts.sec.gov"):
            if "Other+Health+Care" in url:
                return json.dumps(search_payload())

            return json.dumps({"hits": {"total": {"value": 0}, "hits": []}})

        return "<broken"

    filings, problems = fetch_filings(
        "2026-07-01",
        "2026-07-29",
        fetch=fake_fetch,
    )

    assert filings == []
    assert len(problems) == 1
    assert "could not parse" in problems[0]


def test_fetch_drops_a_filing_whose_stated_group_is_not_healthcare() -> None:
    # The search matches text anywhere in the document, so a filing can match
    # the phrase while stating a different industry group.
    non_healthcare = real_filing_xml().replace(
        "Other Health Care", "Other Technology"
    )

    def fake_fetch(url: str) -> str:
        if url.startswith("https://efts.sec.gov"):
            if "Other+Health+Care" in url:
                return json.dumps(search_payload())

            return json.dumps({"hits": {"total": {"value": 0}, "hits": []}})

        return non_healthcare

    filings, problems = fetch_filings(
        "2026-07-01",
        "2026-07-29",
        fetch=fake_fetch,
    )

    assert filings == []
    assert problems == []


def test_search_reports_invalid_json() -> None:
    def fake_fetch(url: str) -> str:
        return "not json"

    filings, problems = fetch_filings(
        "2026-07-01",
        "2026-07-29",
        fetch=fake_fetch,
    )

    assert filings == []
    assert len(problems) == 5
    assert all("invalid JSON" in problem for problem in problems)
