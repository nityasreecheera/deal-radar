from contextlib import closing
from pathlib import Path

import pytest

from src.candidates import (
    count_by_verdict,
    find_by_company,
    get_candidate,
    list_candidates,
    save_candidate,
)
from src.models import Candidate, FormDFiling
from src.seen import connect


def candidate(
    name: str = "Genomenon, Inc.",
    accession: str = "acc-1",
    verdict: str = "fits",
    reason: str = "AI software structuring genetic evidence.",
    amount: int | None = 10_000_000,
    filed_date: str = "2026-07-30",
    **extra,
) -> Candidate:
    filing = FormDFiling(
        accession=accession,
        cik="1",
        company_name=name,
        filed_date=filed_date,
        industry_group="Other Technology",
        city="ANN ARBOR",
        state="MI",
        total_offering_amount=amount,
        year_of_incorporation=2015,
    )

    return Candidate(
        filing=filing,
        verdict=verdict,
        reason=reason,
        **extra,
    )


@pytest.fixture
def db(tmp_path: Path):
    with closing(connect(tmp_path / "radar.sqlite")) as connection:
        yield connection


def test_a_fresh_database_has_no_judgements(db) -> None:
    assert list_candidates(db) == []
    assert count_by_verdict(db) == {}
    assert get_candidate(db, "acc-1") is None


def test_saving_then_reading_back(db) -> None:
    save_candidate(db, candidate(), judged_at="2026-07-30T12:00:00+00:00")

    stored = get_candidate(db, "acc-1")

    assert stored is not None
    assert stored.company_name == "Genomenon, Inc."
    assert stored.verdict == "fits"
    assert stored.reason == "AI software structuring genetic evidence."
    assert stored.offering_amount == 10_000_000
    assert stored.city == "ANN ARBOR"
    assert stored.incorporated == 2015
    assert stored.judged_at == "2026-07-30T12:00:00+00:00"


def test_website_and_description_are_kept(db) -> None:
    save_candidate(
        db,
        candidate(website="https://genomenon.com", description="Genomics AI."),
    )

    stored = get_candidate(db, "acc-1")

    assert stored is not None
    assert stored.website == "https://genomenon.com"
    assert stored.description == "Genomics AI."


def test_rejudging_replaces_the_verdict(db) -> None:
    # A filing judged again on better evidence must not leave a stale opinion.
    save_candidate(db, candidate(verdict="maybe", reason="Too little evidence."))
    save_candidate(db, candidate(verdict="fits", reason="Found their site."))

    stored = get_candidate(db, "acc-1")

    assert stored is not None
    assert stored.verdict == "fits"
    assert stored.reason == "Found their site."
    assert len(list_candidates(db)) == 1


def test_rejudging_does_not_erase_a_website_learned_earlier(db) -> None:
    save_candidate(db, candidate(website="https://genomenon.com"))
    save_candidate(db, candidate(verdict="maybe", reason="Reconsidered."))

    stored = get_candidate(db, "acc-1")

    assert stored is not None
    assert stored.website == "https://genomenon.com"


def test_two_filings_from_one_company_are_both_kept(db) -> None:
    # Each filing is a separate judgement on separate evidence.
    save_candidate(db, candidate(accession="acc-1", filed_date="2025-01-01"))
    save_candidate(db, candidate(accession="acc-2", filed_date="2026-07-30"))

    assert len(list_candidates(db)) == 2


def test_history_for_one_company_is_newest_first(db) -> None:
    save_candidate(db, candidate(accession="acc-1", filed_date="2025-01-01"))
    save_candidate(db, candidate(accession="acc-2", filed_date="2026-07-30"))

    history = find_by_company(db, "Genomenon, Inc.")

    assert [item.accession for item in history] == ["acc-2", "acc-1"]


def test_history_matches_a_differently_written_name(db) -> None:
    save_candidate(db, candidate(name="Genomenon, Inc."))

    # Filed later under a slightly different legal name.
    assert len(find_by_company(db, "Genomenon")) == 1
    assert len(find_by_company(db, "genomenon llc")) == 1


def test_history_of_an_unknown_company_is_empty(db) -> None:
    assert find_by_company(db, "Nobody Inc.") == []


def test_history_of_a_name_with_no_identity_is_empty(db) -> None:
    assert find_by_company(db, "Inc.") == []


def test_listing_can_filter_to_one_verdict(db) -> None:
    save_candidate(db, candidate(accession="a", verdict="fits"))
    save_candidate(db, candidate(accession="b", verdict="no_fit", name="Other Co"))
    save_candidate(db, candidate(accession="c", verdict="maybe", name="Third Co"))

    found = list_candidates(db, verdicts=["fits"])

    assert [item.accession for item in found] == ["a"]


def test_listing_can_filter_to_several_verdicts(db) -> None:
    save_candidate(db, candidate(accession="a", verdict="fits"))
    save_candidate(db, candidate(accession="b", verdict="no_fit", name="Other Co"))
    save_candidate(db, candidate(accession="c", verdict="maybe", name="Third Co"))

    found = list_candidates(db, verdicts=["fits", "maybe"])

    assert {item.accession for item in found} == {"a", "c"}


def test_listing_can_filter_by_date(db) -> None:
    save_candidate(db, candidate(accession="old", filed_date="2025-01-01"))
    save_candidate(db, candidate(accession="new", filed_date="2026-07-30"))

    found = list_candidates(db, since="2026-01-01")

    assert [item.accession for item in found] == ["new"]


def test_listing_is_newest_filing_first(db) -> None:
    save_candidate(db, candidate(accession="old", filed_date="2025-01-01"))
    save_candidate(db, candidate(accession="new", filed_date="2026-07-30"))

    assert [item.accession for item in list_candidates(db)] == ["new", "old"]


def test_listing_respects_a_limit(db) -> None:
    for index in range(5):
        save_candidate(db, candidate(accession=f"acc-{index}", name=f"Co {index}"))

    assert len(list_candidates(db, limit=2)) == 2


def test_verdict_tally(db) -> None:
    save_candidate(db, candidate(accession="a", verdict="fits"))
    save_candidate(db, candidate(accession="b", verdict="fits", name="Other Co"))
    save_candidate(db, candidate(accession="c", verdict="no_fit", name="Third Co"))

    assert count_by_verdict(db) == {"fits": 2, "no_fit": 1}


def test_judgements_persist_across_connections(tmp_path: Path) -> None:
    path = tmp_path / "radar.sqlite"

    with closing(connect(path)) as first:
        save_candidate(first, candidate())

    with closing(connect(path)) as second:
        stored = get_candidate(second, "acc-1")

        assert stored is not None
        assert stored.company_name == "Genomenon, Inc."
