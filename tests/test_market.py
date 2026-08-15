"""
The market as the filings describe it, rather than the radar's own health.

The rule: a benchmark must be honest about what it is made from. Too few
companies, or the wrong companies, and it should say nothing rather than
something plausible.
"""

from contextlib import closing
from pathlib import Path

import pytest

from src.candidates import (
    MIN_FOR_A_BENCHMARK,
    market_view,
    save_candidate,
    summarise_amounts,
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
    category: str = "clinical workflow",
    amount: int | None = 4_000_000,
    state: str = "CA",
    incorporated: int | None = 2024,
    filed_date: str = "2026-08-01",
) -> None:
    save_candidate(
        connection,
        Candidate(
            filing=FormDFiling(
                accession=accession,
                cik="1",
                company_name=f"Co {accession}",
                filed_date=filed_date,
                industry_group="Other Health Care",
                state=state,
                total_offering_amount=amount,
                year_of_incorporation=incorporated,
            ),
            verdict="fits",
            reason="Because.",
            category=category,
        ),
        theme="Healthcare",
    )


def test_a_handful_of_companies_is_not_a_benchmark() -> None:
    # Seven raises is an anecdote. Quoting a median from it would be inventing
    # authority the number does not have.
    assert summarise_amounts([1_000_000] * (MIN_FOR_A_BENCHMARK - 1)).median is None
    assert summarise_amounts([1_000_000] * MIN_FOR_A_BENCHMARK).median is not None


def test_quartiles_describe_the_middle_of_the_market() -> None:
    sizes = summarise_amounts([1, 2, 3, 4, 5, 6, 7, 8, 9, 100_000_000])

    assert sizes.count == 10
    assert sizes.median == 5
    assert sizes.smallest == 1
    assert sizes.largest == 100_000_000
    # The outlier moves the top of the range, not the middle of it.
    assert sizes.upper_quartile < 1_000


def test_undisclosed_raises_are_left_out_rather_than_counted_as_zero(db) -> None:
    for n in range(MIN_FOR_A_BENCHMARK):
        store(db, f"acc-{n}", amount=2_000_000)

    store(db, "quiet", amount=None)

    view = market_view(db)

    # Nine companies, eight amounts. A missing number is not a raise of nothing.
    assert view.companies == MIN_FOR_A_BENCHMARK + 1
    assert view.deal_sizes.count == MIN_FOR_A_BENCHMARK
    assert view.deal_sizes.median == 2_000_000


def test_companies_outside_the_market_do_not_move_the_benchmark(db) -> None:
    for n in range(MIN_FOR_A_BENCHMARK):
        store(db, f"health-{n}", amount=2_000_000)

    # An animation studio and something nobody could identify. Both real
    # filings, both cost money to look up, neither is this market.
    store(db, "animation", category="not healthcare", amount=90_000_000)
    store(db, "mystery", category="unclear", amount=90_000_000)

    view = market_view(db)

    assert view.companies == MIN_FOR_A_BENCHMARK
    assert view.deal_sizes.median == 2_000_000
    assert view.deal_sizes.largest == 2_000_000


def test_a_category_needs_enough_companies_of_its_own(db) -> None:
    for n in range(MIN_FOR_A_BENCHMARK):
        store(db, f"flow-{n}", category="clinical workflow")

    for n in range(3):
        store(db, f"virtual-{n}", category="virtual care")

    view = market_view(db)

    assert "clinical workflow" in view.by_category
    # Three is not a benchmark, so it is absent rather than misleading.
    assert "virtual care" not in view.by_category


def test_company_age_is_measured_from_the_latest_filing(db) -> None:
    store(db, "new", incorporated=2026, filed_date="2026-08-01")
    store(db, "young", incorporated=2025, filed_date="2026-08-01")
    store(db, "older", incorporated=2019, filed_date="2026-08-01")

    ages = market_view(db).company_age

    assert ages["founded this year"] == 1
    assert ages["1 to 2 years"] == 1
    assert ages["older"] == 1


def test_locations_are_ranked_and_capped(db) -> None:
    for n in range(5):
        store(db, f"ca-{n}", state="CA")
    for n in range(2):
        store(db, f"ma-{n}", state="MA")

    places = market_view(db).locations

    assert places[0] == {"state": "CA", "companies": 5}
    assert places[1] == {"state": "MA", "companies": 2}


def test_an_empty_database_says_nothing(db) -> None:
    view = market_view(db)

    assert view.companies == 0
    assert view.deal_sizes.median is None


def test_a_company_judged_by_several_domains_is_counted_once(db) -> None:
    """
    Across all domains, a company with three judgements would land in the
    amounts list three times and quietly weight the median toward whatever
    interests several theses at once. Reading one domain this never arose.
    """
    for n in range(MIN_FOR_A_BENCHMARK):
        store(db, f"acc-{n}", amount=2_000_000)

    # One company, judged by three domains, raising far more than the rest.
    for theme in ("Healthcare", "AI tools", "AI infra"):
        save_candidate(
            db,
            Candidate(
                filing=FormDFiling(
                    accession="shared",
                    cik="1",
                    company_name="Cornelis Networks, Inc.",
                    filed_date="2026-08-01",
                    industry_group="Other Technology",
                    total_offering_amount=245_000_000,
                ),
                verdict="fits",
                reason="Because.",
                category="clinical workflow",
            ),
            theme=theme,
        )

    view = market_view(db)

    # Nine companies, not eleven.
    assert view.companies == MIN_FOR_A_BENCHMARK + 1
    assert view.deal_sizes.count == MIN_FOR_A_BENCHMARK + 1
