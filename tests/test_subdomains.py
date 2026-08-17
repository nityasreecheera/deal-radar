"""
Dividing a domain by its own criteria.

The global category list has seven buckets for healthcare and one for energy,
because healthcare was written first. So Energy's eighteen companies all land in
"energy and climate" and the breakdown says nothing. A thesis's own "looking for"
lines are the right divisions — and they move when someone edits the criteria,
which is the point.
"""

from contextlib import closing
from pathlib import Path

import pytest

from src.candidates import save_candidate, subdomain_counts
from src.judge import matched_line
from src.models import Candidate, FormDFiling
from src.seen import connect
from src.thesis import Thesis


def energy() -> Thesis:
    return Thesis(
        domain="Energy",
        name="Energy, climate and grid technology",
        description="The energy transition.",
        include=[
            "batteries, storage, and the materials that go into them",
            "solar, wind, geothermal, and nuclear technology",
            "grid software, demand response, and virtual power plants",
        ],
    )


@pytest.fixture
def db(tmp_path: Path):
    with closing(connect(tmp_path / "radar.sqlite")) as connection:
        yield connection


def test_a_line_copied_back_exactly_is_kept() -> None:
    thesis = energy()

    assert (
        matched_line("solar, wind, geothermal, and nuclear technology", thesis)
        == "solar, wind, geothermal, and nuclear technology"
    )


def test_case_and_whitespace_do_not_break_the_match() -> None:
    assert matched_line(
        "  Solar, Wind, Geothermal, And Nuclear Technology  ", energy()
    ) == "solar, wind, geothermal, and nuclear technology"


def test_a_dropped_trailing_clause_still_matches() -> None:
    # Models shorten a line far more often than they invent a new one.
    assert matched_line("batteries, storage", energy()) == (
        "batteries, storage, and the materials that go into them"
    )


def test_an_invented_division_is_refused() -> None:
    # The one thing this must not do: create a sub-division nobody wrote, which
    # fragments the counting it exists to produce.
    assert matched_line("fusion reactors", energy()) is None
    assert matched_line("", energy()) is None
    assert matched_line(None, energy()) is None


def store(connection, accession, subdomain, amount=1_000_000, verdict="fits"):
    save_candidate(
        connection,
        Candidate(
            filing=FormDFiling(
                accession=accession,
                cik="1",
                company_name=f"Co {accession}",
                filed_date="2026-08-01",
                industry_group="Other Energy",
                total_offering_amount=amount,
            ),
            verdict=verdict,
            reason="Because.",
            subdomain=subdomain,
        ),
        theme="Energy",
    )


def test_a_domain_divides_by_its_own_lines(db) -> None:
    store(db, "a", "batteries, storage, and the materials that go into them")
    store(db, "b", "batteries, storage, and the materials that go into them")
    store(db, "c", "solar, wind, geothermal, and nuclear technology", amount=9_000_000)

    counts = subdomain_counts(db, "Energy")

    assert counts[0]["subdomain"].startswith("batteries")
    assert counts[0]["companies"] == 2
    assert counts[1]["companies"] == 1
    assert counts[1]["raised"] == 9_000_000


def test_rejected_companies_are_left_out_by_default(db) -> None:
    store(db, "a", "batteries, storage, and the materials that go into them")
    store(db, "b", "batteries, storage, and the materials that go into them",
          verdict="no_fit")

    assert subdomain_counts(db, "Energy")[0]["companies"] == 1
    assert subdomain_counts(db, "Energy", fits_only=False)[0]["companies"] == 2


def test_a_company_with_no_matched_line_is_not_counted(db) -> None:
    store(db, "a", None)

    assert subdomain_counts(db, "Energy") == []
