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
    MAX_CLUSTERS_REPORTED,
    CategoryContext,
    category_context,
    category_counts,
    category_lines,
    describe_category,
    describe_rejection_clusters,
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


def test_the_footer_names_what_you_keep_rejecting(db) -> None:
    for n in range(5):
        store(db, f"drug-{n}", "drug development")
    for n in range(3):
        store(db, f"dev-{n}", "medical devices")

    line = describe_rejection_clusters(db)

    assert "5 drug development" in line
    assert "3 medical devices" in line
    assert "8 companies looked up to reject" in line


def test_a_category_that_has_ever_fitted_is_not_suggested_as_a_rule(db) -> None:
    # Proxima Bio is drug development and it fit. Telling someone to filter out
    # drug development would be telling them to filter out what they want.
    for n in range(4):
        store(db, f"drug-{n}", "drug development")

    store(db, "drug-good", "drug development", verdict="fits")

    assert describe_rejection_clusters(db) == ""


def test_a_rescued_company_removes_its_category_from_the_footer(db) -> None:
    for n in range(4):
        store(db, f"acc-{n}", "medical devices")

    assert "medical devices" in describe_rejection_clusters(db)

    # The analyst overrules one. The category is no longer a clean rule.
    record_decision(db, "acc-0", verdict="fits")

    assert describe_rejection_clusters(db) == ""


def test_a_quiet_quarter_produces_no_footer(db) -> None:
    store(db, "acc-1", "medical devices")
    store(db, "acc-2", "medical devices")

    assert describe_rejection_clusters(db) == ""


def test_the_footer_is_capped(db) -> None:
    for category in (
        "drug development",
        "medical devices",
        "life sciences tools",
        "healthcare services",
        "not healthcare",
    ):
        for n in range(3):
            store(db, f"{category}-{n}", category)

    line = describe_rejection_clusters(db)

    # Five categories qualify, four are named — but the total counts them all.
    assert line.count(" 3 ") <= MAX_CLUSTERS_REPORTED
    assert "15 companies looked up to reject" in line


def test_judgements_are_filed_under_the_short_domain_label(db) -> None:
    """
    The label rows are stored under, and the one queries must use.

    Thesis has both `domain` ("Healthcare") and `name` ("Healthcare AI and
    clinical software"). Rows carry `domain`. Filtering on `name` matches
    nothing — and matches nothing *silently*, so the category lines simply never
    appeared in the email and everything looked like it was working. This test
    exists so that stays fixed.
    """
    from src.thesis import Thesis

    thesis = Thesis(
        domain="Healthcare",
        name="Healthcare AI and clinical software",
        description="Software used in care delivery.",
        include=["clinical software"],
    )

    for n in range(4):
        store(db, f"acc-{n}", "medical devices")

    # Rows were saved with theme="Healthcare" by the store() helper, matching
    # what the pipeline does.
    assert category_context(db, "medical devices", theme=thesis.domain).seen == 4
    assert category_context(db, "medical devices", theme=thesis.name).seen == 0

    assert describe_rejection_clusters(db, theme=thesis.domain) != ""
    assert describe_rejection_clusters(db, theme=thesis.name) == ""


def make(accession: str, category: str) -> Candidate:
    return Candidate(
        filing=FormDFiling(
            accession=accession,
            cik="1",
            company_name=f"Co {accession}",
            filed_date="2026-08-14",
            industry_group="Other Technology",
        ),
        verdict="fits",
        reason="Because.",
        category=category,
    )


def test_several_of_a_kind_at_once_is_said_once(db) -> None:
    # The real bug: three AI infrastructure companies arrived in one digest and
    # each was told it was "the 3rd you've seen", which was true of none of them.
    arriving = [make(f"acc-{n}", "ai infrastructure") for n in range(3)]

    for candidate in arriving:
        save_candidate(db, candidate, theme="AI tools")

    lines = category_lines(db, arriving, theme="AI tools")

    assert len(lines) == 1
    line = next(iter(lines.values()))

    assert "3 ai infrastructure companies in this digest" in line
    assert "the first of these you've seen" in line
    assert "3rd" not in line


def test_arriving_together_counts_the_ones_seen_before(db) -> None:
    for n in range(4):
        store(db, f"old-{n}", "developer tools")

    arriving = [make(f"new-{n}", "developer tools") for n in range(2)]

    for candidate in arriving:
        save_candidate(db, candidate, theme="Healthcare")

    line = next(iter(category_lines(db, arriving).values()))

    assert "2 developer tools companies in this digest" in line
    assert "making 6" in line


def test_one_of_a_kind_still_reads_as_an_ordinal(db) -> None:
    for n in range(3):
        store(db, f"old-{n}", "medical devices")

    arriving = [make("new", "medical devices")]
    save_candidate(db, arriving[0], theme="Healthcare")

    line = next(iter(category_lines(db, arriving).values()))

    assert "The 4th medical devices company" in line


def test_companies_with_no_category_are_skipped(db) -> None:
    candidate = make("acc-1", "unclear")
    save_candidate(db, candidate, theme="Healthcare")

    assert category_lines(db, [candidate]) == {}
