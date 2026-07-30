from contextlib import closing
from pathlib import Path

import pytest

from src.models import FormDFiling
from src.seen import (
    connect,
    count_seen,
    filter_unseen,
    is_seen,
    mark_seen,
)


def filing(name: str, accession: str = "acc-1") -> FormDFiling:
    return FormDFiling(
        accession=accession,
        cik="1",
        company_name=name,
        filed_date="2026-07-27",
        industry_group="Other Health Care",
    )


@pytest.fixture
def db(tmp_path: Path):
    with closing(connect(tmp_path / "radar.sqlite")) as connection:
        yield connection


def test_a_fresh_index_is_empty(db) -> None:
    assert count_seen(db) == 0
    assert is_seen(db, "PreventiveMD, Inc.") is False


def test_marking_then_checking(db) -> None:
    mark_seen(db, "PreventiveMD, Inc.", source="form_d")

    assert is_seen(db, "PreventiveMD, Inc.") is True
    assert count_seen(db) == 1


def test_name_variants_are_the_same_company(db) -> None:
    mark_seen(db, "PreventiveMD, Inc.", source="form_d")

    # Suffixes and punctuation must not create a second identity.
    assert is_seen(db, "PreventiveMD") is True
    assert is_seen(db, "preventivemd llc") is True
    assert is_seen(db, "Preventive MD, Inc.") is True


def test_a_different_company_is_not_seen(db) -> None:
    mark_seen(db, "PreventiveMD, Inc.", source="form_d")

    assert is_seen(db, "Wesper Inc.") is False


def test_domain_identifies_a_company_under_another_name(db) -> None:
    mark_seen(
        db,
        "PreventiveMD, Inc.",
        source="form_d",
        website="https://www.preventivemd.com/about",
    )

    # Renamed, rebranded, or filed under a subsidiary — the domain still matches.
    assert is_seen(db, "Something Else Entirely", "https://preventivemd.com") is True


def test_remarking_preserves_the_first_sighting(db) -> None:
    first = mark_seen(
        db,
        "PreventiveMD, Inc.",
        source="form_d",
        first_seen="2026-07-01T00:00:00+00:00",
    )
    second = mark_seen(
        db,
        "PreventiveMD, Inc.",
        source="digest",
        first_seen="2026-07-29T00:00:00+00:00",
    )

    assert first.first_seen == second.first_seen == "2026-07-01T00:00:00+00:00"
    assert count_seen(db) == 1


def test_remarking_fills_in_a_domain_learned_later(db) -> None:
    # A Form D never carries a website; enrichment supplies it afterwards.
    mark_seen(db, "PreventiveMD, Inc.", source="form_d")

    assert is_seen(db, "x", "https://preventivemd.com") is False

    mark_seen(
        db,
        "PreventiveMD, Inc.",
        source="enrichment",
        website="https://preventivemd.com",
    )

    assert is_seen(db, "x", "https://preventivemd.com") is True


def test_remarking_does_not_erase_a_known_domain(db) -> None:
    mark_seen(
        db,
        "PreventiveMD, Inc.",
        source="enrichment",
        website="https://preventivemd.com",
    )
    mark_seen(db, "PreventiveMD, Inc.", source="form_d")

    assert is_seen(db, "x", "https://preventivemd.com") is True


def test_a_name_with_no_letters_or_digits_is_rejected(db) -> None:
    with pytest.raises(ValueError):
        mark_seen(db, "---", source="form_d")


def test_a_name_that_normalises_to_nothing_is_never_seen(db) -> None:
    # "Inc" alone strips to an empty identity; it must not match everything.
    assert is_seen(db, "Inc.") is False


def test_filter_unseen_keeps_only_new_companies(db) -> None:
    mark_seen(db, "PreventiveMD, Inc.", source="form_d")

    fresh, skipped = filter_unseen(
        db,
        [filing("PreventiveMD, Inc."), filing("Wesper Inc.")],
    )

    assert [f.company_name for f in fresh] == ["Wesper Inc."]
    assert skipped == 1


def test_filter_unseen_deduplicates_within_one_batch(db) -> None:
    # The same company can file twice in one window. Showing it twice in one
    # digest is as wrong as showing it on two consecutive days.
    fresh, skipped = filter_unseen(
        db,
        [
            filing("Wesper Inc.", "a"),
            filing("Wesper, Inc.", "b"),
            filing("Wesper", "c"),
        ],
    )

    assert len(fresh) == 1
    assert skipped == 2


def test_filter_unseen_on_an_empty_batch(db) -> None:
    assert filter_unseen(db, []) == ([], 0)


def test_filter_unseen_does_not_mark_anything(db) -> None:
    # Filtering answers a question; recording is a separate, explicit step.
    filter_unseen(db, [filing("Wesper Inc.")])

    assert count_seen(db) == 0


def test_the_index_persists_across_connections(tmp_path: Path) -> None:
    path = tmp_path / "radar.sqlite"

    with closing(connect(path)) as first:
        mark_seen(first, "PreventiveMD, Inc.", source="form_d")

    with closing(connect(path)) as second:
        assert is_seen(second, "PreventiveMD") is True
        assert count_seen(second) == 1
