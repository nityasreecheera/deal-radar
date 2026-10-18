"""
Positive signals from later filings by companies already judged.
"""

from datetime import date
from pathlib import Path

import pytest

from src.archive import save_filing
from src.candidates import save_candidate
from src.models import Candidate, FormDFiling, RelatedPerson
from src.momentum import (
    alerts_for,
    detect,
    facts_between,
    highlights,
    mark_sent,
    render_section,
    unsent,
)
from src.seen import connect
from src.visibility import apply_public_view


TODAY = date(2026, 10, 18)


def filing(
    accession: str,
    filed: str,
    offering: int | None = 2_000_000,
    sold: int | None = 0,
    investors: int | None = 3,
    amendment: bool = False,
    people: list[RelatedPerson] | None = None,
    cik: str = "0000000042",
    name: str = "Acme Robotics, Inc.",
) -> FormDFiling:
    return FormDFiling(
        accession=accession,
        cik=cik,
        company_name=name,
        filed_date=filed,
        industry_group="Other Technology",
        total_offering_amount=offering,
        total_amount_sold=sold,
        investor_count=investors,
        is_amendment=amendment,
        related_persons=people or [],
    )


def as_dict(f: FormDFiling) -> dict:
    return f.model_dump(mode="json")


@pytest.fixture
def db(tmp_path: Path):
    connection = connect(tmp_path / "radar.sqlite")
    yield connection
    connection.close()


def judge(connection, first: FormDFiling, verdict: str, theme: str = "AI infra") -> None:
    """The company's first filing, judged under a domain."""
    save_filing(connection, first)
    save_candidate(
        connection,
        Candidate(filing=first, verdict=verdict, reason="Because."),
        theme=theme,
    )


# ── what counts as a signal ──────────────────────────────────────────────


def test_a_first_filing_is_not_a_signal() -> None:
    assert facts_between(as_dict(filing("a2", "2026-10-15")), []) == []


def test_a_round_twice_as_big_is_strong() -> None:
    facts = facts_between(
        as_dict(filing("a2", "2026-10-15", offering=10_000_000)),
        [as_dict(filing("a1", "2026-06-01", offering=2_000_000))],
    )

    assert facts[0].kind == "bigger_round"
    assert facts[0].strong
    assert "5x" in facts[0].text


def test_an_ordinary_new_round_is_noted_but_not_strong() -> None:
    facts = facts_between(
        as_dict(filing("a2", "2026-10-15", offering=2_500_000)),
        [as_dict(filing("a1", "2026-06-01", offering=2_000_000))],
    )

    assert [f.kind for f in facts] == ["new_round"]
    assert not facts[0].strong


def test_a_second_filing_within_a_month_is_not_a_new_round() -> None:
    # Usually the same raise filed twice, or a correction.
    facts = facts_between(
        as_dict(filing("a2", "2026-06-10", offering=9_000_000)),
        [as_dict(filing("a1", "2026-06-01", offering=2_000_000))],
    )

    assert facts == []


def test_an_amendment_that_fills_the_round_is_strong() -> None:
    facts = facts_between(
        as_dict(filing("a2", "2026-08-01", offering=3_000_000, sold=3_000_000, amendment=True)),
        [as_dict(filing("a1", "2026-06-01", offering=3_000_000, sold=500_000))],
    )

    assert facts[0].kind == "round_filled"
    assert facts[0].strong


def test_a_tiny_round_filling_is_noise() -> None:
    facts = facts_between(
        as_dict(filing("a2", "2026-08-01", offering=100, sold=100, amendment=True)),
        [as_dict(filing("a1", "2026-06-01", offering=100, sold=0))],
    )

    assert facts == []


def test_a_jump_in_amount_sold_is_strong() -> None:
    facts = facts_between(
        as_dict(filing("a2", "2026-08-01", offering=20_000_000, sold=6_000_000, amendment=True)),
        [as_dict(filing("a1", "2026-06-01", offering=20_000_000, sold=1_000_000))],
    )

    assert facts[0].kind == "sold_jump"
    assert facts[0].strong


def test_a_new_director_is_noted() -> None:
    old = RelatedPerson(first_name="Ada", last_name="Lovelace", relationships=["Executive Officer"])
    new = RelatedPerson(first_name="Grace", last_name="Hopper", relationships=["Director"])

    facts = facts_between(
        as_dict(filing("a2", "2026-08-01", amendment=True, people=[old, new])),
        [as_dict(filing("a1", "2026-06-01", people=[old]))],
    )

    assert any(f.kind == "new_people" and "Grace Hopper" in f.text for f in facts)


# ── who hears about it ───────────────────────────────────────────────────


def test_detection_reads_the_archive_and_skips_the_judged_filing(db) -> None:
    judge(db, filing("a1", "2026-06-01", offering=2_000_000), "fits")
    save_filing(db, filing("a2", "2026-10-15", offering=10_000_000))

    found = detect(db, "2026-06-01")

    assert [s.accession for s in found] == ["a2"]
    # Each filing once: a second pass finds nothing new.
    assert detect(db, "2026-06-01") == []


def test_a_rejected_company_returns_only_on_a_strong_signal(db) -> None:
    judge(db, filing("a1", "2026-06-01", offering=2_000_000, cik="1", name="Weak Co"), "no_fit")
    save_filing(db, filing("a2", "2026-10-15", offering=2_500_000, cik="1", name="Weak Co"))

    judge(db, filing("b1", "2026-06-01", offering=2_000_000, cik="2", name="Strong Co"), "no_fit")
    save_filing(db, filing("b2", "2026-10-15", offering=20_000_000, cik="2", name="Strong Co"))

    detect(db, "2026-06-01")
    names = [h.company_name for h in highlights(db, today=TODAY)]

    assert names == ["Strong Co"]


def test_fits_and_maybes_hear_about_any_signal(db) -> None:
    judge(db, filing("a1", "2026-06-01", offering=2_000_000), "maybe")
    save_filing(db, filing("a2", "2026-10-15", offering=2_500_000))

    detect(db, "2026-06-01")

    assert [h.kind for h in highlights(db, today=TODAY)] == ["new_round"]


def test_highlights_roll_off_after_a_week(db) -> None:
    judge(db, filing("a1", "2026-06-01", offering=2_000_000), "fits")
    save_filing(db, filing("a2", "2026-10-01", offering=10_000_000))
    detect(db, "2026-06-01")

    assert highlights(db, today=date(2026, 10, 5))
    assert highlights(db, today=TODAY) == []


def test_strong_signals_rank_first(db) -> None:
    judge(db, filing("a1", "2026-06-01", offering=2_000_000, cik="1", name="Steady Co"), "fits")
    save_filing(db, filing("a2", "2026-10-16", offering=50_000_000, cik="1", name="Steady Co"))
    save_filing(db, filing("a2x", "2026-10-17", offering=2_100_000, cik="3", name="Quiet Co"))
    judge(db, filing("c1", "2026-06-01", offering=2_000_000, cik="3", name="Quiet Co"), "fits")
    detect(db, "2026-06-01")

    ranked = highlights(db, today=TODAY)

    assert ranked[0].company_name == "Steady Co"
    assert ranked[0].strong


def test_the_alert_symbol_is_for_strong_signals_only(db) -> None:
    judge(db, filing("a1", "2026-06-01", offering=2_000_000, cik="1"), "fits")
    save_filing(db, filing("a2", "2026-10-15", offering=2_500_000, cik="1"))
    judge(db, filing("b1", "2026-06-01", offering=2_000_000, cik="2", name="B"), "fits")
    save_filing(db, filing("b2", "2026-10-15", offering=20_000_000, cik="2", name="B"))
    detect(db, "2026-06-01")

    alerts = alerts_for(db, ["0001", "0002"], today=TODAY)

    assert set(alerts) == {"2"}
    assert "10x" in alerts["2"]


# ── privacy and email ────────────────────────────────────────────────────


def test_a_private_domains_signals_never_reach_a_visitor(db) -> None:
    judge(db, filing("a1", "2026-06-01", offering=2_000_000), "fits", theme="Parallax")
    save_filing(db, filing("a2", "2026-10-15", offering=20_000_000))
    detect(db, "2026-06-01")

    assert highlights(db, today=TODAY)

    apply_public_view(db, hidden=["Parallax"])

    assert highlights(db, today=TODAY) == []
    assert alerts_for(db, ["42"], today=TODAY) == {}
    assert db.execute("SELECT COUNT(*) FROM momentum_signal").fetchone()[0] == 0


def test_a_signal_is_emailed_once_per_domain(db) -> None:
    judge(db, filing("a1", "2026-06-01", offering=2_000_000), "fits")
    save_filing(db, filing("a2", "2026-10-15", offering=20_000_000))
    detect(db, "2026-06-01")

    waiting = unsent(db, "AI infra", today=TODAY)
    assert [s.accession for s in waiting] == ["a2"]
    assert "Acme Robotics" in render_section(waiting)

    mark_sent(db, "AI infra", ["a2"])

    assert unsent(db, "AI infra", today=TODAY) == []


def test_no_signals_means_no_section() -> None:
    assert render_section([]) == ""
