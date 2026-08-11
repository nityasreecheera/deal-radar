"""
Counting a company against the ones like it.

The rule these protect: a count is only worth printing when it says something a
single company could not, and it must reflect what the analyst decided rather
than what the model did.
"""

from contextlib import closing
from pathlib import Path

import pytest

from src.candidates import (
    CategoryContext,
    category_context,
    category_counts,
    describe_category,
    ordinal_suffix,
    quarter_start,
    record_decision,
    save_candidate,
)
from src.models import Candidate, FormDFiling
from src.seen import connect


@pytest.fixture
def db(tmp_path: Path):
    with closing(connect(tmp_path / "radar.sqlite")) as connection:
        yield connection


def store(
    connection,
    accession: str,
    category: str,
    verdict: str = "no_fit",
    filed_date: str = "2026-07-15",
    name: str | None = None,
) -> Candidate:
    candidate = Candidate(
        filing=FormDFiling(
            accession=accession,
            cik="1",
            company_name=name or f"Co {accession}",
            filed_date=filed_date,
            industry_group="Other Health Care",
        ),
        verdict=verdict,
        reason="Because.",
        category=category,
    )

    save_candidate(connection, candidate, theme="Healthcare")

    return candidate


def test_a_category_is_counted_across_companies(db) -> None:
    for n in range(4):
        store(db, f"acc-{n}", "drug development")

    context = category_context(db, "drug development")

    assert context.seen == 4
    assert context.rejected == 4


def test_the_line_names_the_count_and_what_you_did(db) -> None:
    for n in range(4):
        store(db, f"acc-{n}", "drug development")

    line = category_context(db, "drug development").describe()

    assert "4th drug development company" in line
    assert "passed on" in line


def test_two_of_something_is_not_worth_saying(db) -> None:
    # A count of two is a coincidence. Printing it adds a line to the email
    # without adding anything to know.
    for n in range(2):
        store(db, f"acc-{n}", "virtual care")

    assert category_context(db, "virtual care").describe() == ""


def test_unclear_is_never_reported(db) -> None:
    for n in range(6):
        store(db, f"acc-{n}", "unclear")

    assert category_context(db, "unclear").describe() == ""


def test_counting_follows_the_analysts_verdict_not_the_models(db) -> None:
    # The analyst rescued one. Reporting "you passed on all 3" would be telling
    # them their own history wrongly.
    for n in range(3):
        store(db, f"acc-{n}", "clinical workflow", verdict="no_fit")

    record_decision(db, "acc-0", verdict="fits")

    context = category_context(db, "clinical workflow")

    assert context.seen == 3
    assert context.fitted == 1
    assert context.rejected == 2
    assert "1 of them fit" in context.describe()


def test_the_window_excludes_older_companies(db) -> None:
    store(db, "old-1", "drug development", filed_date="2026-01-10")
    store(db, "old-2", "drug development", filed_date="2026-02-10")
    store(db, "new-1", "drug development", filed_date="2026-07-20")

    assert category_context(db, "drug development").seen == 3
    assert category_context(db, "drug development", since="2026-07-01").seen == 1


def test_a_company_with_no_category_says_nothing(db) -> None:
    assert category_context(db, None).describe() == ""
    assert category_context(db, "").seen == 0


def test_category_counts_ranks_the_busiest_first(db) -> None:
    for n in range(5):
        store(db, f"drug-{n}", "drug development")
    for n in range(2):
        store(db, f"flow-{n}", "clinical workflow")

    counts = category_counts(db)

    assert [c.category for c in counts] == [
        "drug development",
        "clinical workflow",
    ]
    assert counts[0].seen == 5


def test_describe_category_reads_the_candidates_own_category(db) -> None:
    for n in range(3):
        store(db, f"acc-{n}", "medical devices")

    candidate = store(db, "acc-9", "medical devices")

    line = describe_category(db, candidate)

    assert "4th medical devices company" in line


def test_the_quarter_is_the_window(db) -> None:
    assert quarter_start("2026-08-11") == "2026-07-01"
    assert quarter_start("2026-01-05") == "2026-01-01"
    assert quarter_start("2026-12-31") == "2026-10-01"


def test_ordinals_handle_the_teens() -> None:
    # 11th, not 11st. The usual trap.
    assert ordinal_suffix(11) == "th"
    assert ordinal_suffix(12) == "th"
    assert ordinal_suffix(13) == "th"
    assert ordinal_suffix(21) == "st"
    assert ordinal_suffix(3) == "rd"


def test_a_category_with_both_outcomes_reports_the_fits(db) -> None:
    context = CategoryContext(
        category="clinical workflow", seen=5, rejected=3, fitted=2
    )

    assert "5th clinical workflow company" in context.describe()
    assert "2 of them fit" in context.describe()
