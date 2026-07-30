from contextlib import closing
from pathlib import Path

import pytest

from src.candidates import (
    count_unread,
    date_range,
    known_themes,
    list_candidates,
    mark_all_viewed,
    mark_viewed,
    save_candidate,
)
from src.models import Candidate, FormDFiling
from src.seen import connect


def candidate(
    name: str = "Genomenon, Inc.",
    accession: str = "acc-1",
    verdict: str = "fits",
    filed_date: str = "2026-07-30",
) -> Candidate:
    return Candidate(
        filing=FormDFiling(
            accession=accession,
            cik="1",
            company_name=name,
            filed_date=filed_date,
            industry_group="Other Technology",
            total_offering_amount=1_000_000,
        ),
        verdict=verdict,
        reason="A reason.",
    )


@pytest.fixture
def db(tmp_path: Path):
    with closing(connect(tmp_path / "radar.sqlite")) as connection:
        yield connection


def test_a_new_judgement_is_unread(db) -> None:
    stored = save_candidate(db, candidate(), theme="Healthcare")

    assert stored.viewed_at is None
    assert stored.is_unread is True
    assert count_unread(db) == 1


def test_marking_viewed(db) -> None:
    save_candidate(db, candidate(), theme="Healthcare")

    stored = mark_viewed(db, "acc-1", viewed_at="2026-07-30T09:00:00+00:00")

    assert stored is not None
    assert stored.viewed_at == "2026-07-30T09:00:00+00:00"
    assert stored.is_unread is False
    assert count_unread(db) == 0


def test_the_first_reading_is_the_one_kept(db) -> None:
    # Re-opening something does not make it newly read.
    save_candidate(db, candidate(), theme="Healthcare")

    mark_viewed(db, "acc-1", viewed_at="2026-07-30T09:00:00+00:00")
    stored = mark_viewed(db, "acc-1", viewed_at="2026-08-05T09:00:00+00:00")

    assert stored is not None
    assert stored.viewed_at == "2026-07-30T09:00:00+00:00"


def test_marking_an_unknown_filing_returns_nothing(db) -> None:
    assert mark_viewed(db, "no-such-accession") is None


def test_rejudging_does_not_mark_it_unread_again(db) -> None:
    save_candidate(db, candidate(), theme="Healthcare")
    mark_viewed(db, "acc-1")

    save_candidate(db, candidate(verdict="maybe"), theme="Healthcare")

    assert count_unread(db) == 0


def test_unread_only_filter(db) -> None:
    save_candidate(db, candidate(accession="a"), theme="Healthcare")
    save_candidate(
        db, candidate(accession="b", name="Other Co"), theme="Healthcare"
    )

    mark_viewed(db, "a")

    unread = list_candidates(db, unread_only=True)

    assert [item.accession for item in unread] == ["b"]


def test_mark_all_viewed_reports_how_many_changed(db) -> None:
    save_candidate(db, candidate(accession="a"), theme="Healthcare")
    save_candidate(
        db, candidate(accession="b", name="Other Co"), theme="Healthcare"
    )
    mark_viewed(db, "a")

    assert mark_all_viewed(db) == 1
    assert count_unread(db) == 0


def test_mark_all_viewed_can_be_scoped_to_one_theme(db) -> None:
    save_candidate(db, candidate(accession="a"), theme="Healthcare")
    save_candidate(db, candidate(accession="b", name="Chip Co"), theme="Chips")

    assert mark_all_viewed(db, theme="Healthcare") == 1
    assert count_unread(db) == 1
    assert count_unread(db, theme="Chips") == 1
    assert count_unread(db, theme="Healthcare") == 0


def test_theme_filter(db) -> None:
    save_candidate(db, candidate(accession="a"), theme="Healthcare")
    save_candidate(db, candidate(accession="b", name="Chip Co"), theme="Chips")

    found = list_candidates(db, theme="Chips")

    assert [item.company_name for item in found] == ["Chip Co"]


def test_known_themes_comes_from_the_data(db) -> None:
    # The dropdown should reflect what has actually run, not what is configured.
    save_candidate(db, candidate(accession="a"), theme="Healthcare")
    save_candidate(db, candidate(accession="b", name="Chip Co"), theme="Chips")
    save_candidate(db, candidate(accession="c", name="Old Co"), theme=None)

    assert known_themes(db) == ["Chips", "Healthcare"]


def test_date_filters_bound_both_ends(db) -> None:
    save_candidate(
        db, candidate(accession="a", filed_date="2026-06-01"), theme="H"
    )
    save_candidate(
        db,
        candidate(accession="b", name="Mid Co", filed_date="2026-07-15"),
        theme="H",
    )
    save_candidate(
        db,
        candidate(accession="c", name="Late Co", filed_date="2026-08-01"),
        theme="H",
    )

    found = list_candidates(db, since="2026-07-01", until="2026-07-31")

    assert [item.accession for item in found] == ["b"]


def test_date_range_gives_the_calendar_its_bounds(db) -> None:
    save_candidate(
        db, candidate(accession="a", filed_date="2026-06-01"), theme="H"
    )
    save_candidate(
        db,
        candidate(accession="b", name="Late Co", filed_date="2026-08-01"),
        theme="H",
    )

    assert date_range(db) == ("2026-06-01", "2026-08-01")


def test_date_range_of_an_empty_database(db) -> None:
    assert date_range(db) == (None, None)


def test_filters_combine(db) -> None:
    save_candidate(
        db,
        candidate(accession="a", verdict="fits", filed_date="2026-07-15"),
        theme="Healthcare",
    )
    save_candidate(
        db,
        candidate(
            accession="b", name="No Co", verdict="no_fit", filed_date="2026-07-16"
        ),
        theme="Healthcare",
    )
    save_candidate(
        db,
        candidate(accession="c", name="Chip Co", verdict="fits"),
        theme="Chips",
    )
    mark_viewed(db, "a")

    found = list_candidates(
        db,
        verdicts=["fits"],
        theme="Healthcare",
        since="2026-07-01",
        unread_only=True,
    )

    # 'a' fits and is in theme but has been read; 'b' is the wrong verdict;
    # 'c' is the wrong theme.
    assert found == []
