"""
The analyst's own call, kept alongside the model's.

The rule these all protect: a human decision must survive anything the model
does later, and must win everywhere the verdict is read.
"""

from contextlib import closing
from pathlib import Path

import pytest

from src.candidates import (
    clear_verdict,
    disagreements,
    get_candidate,
    list_candidates,
    record_decision,
    save_candidate,
)
from src.models import Candidate, FormDFiling
from src.seen import connect


@pytest.fixture
def db(tmp_path: Path):
    with closing(connect(tmp_path / "radar.sqlite")) as connection:
        yield connection


def store(connection, accession="acc-1", name="Acme Health, Inc.", verdict="no_fit"):
    save_candidate(
        connection,
        Candidate(
            filing=FormDFiling(
                accession=accession,
                cik="1",
                company_name=name,
                filed_date="2026-07-28",
                industry_group="Other Health Care",
                total_offering_amount=2_000_000,
            ),
            verdict=verdict,
            reason="Model's reasoning.",
        ),
        theme="healthcare",
    )


def test_a_note_is_saved_and_read_back(db) -> None:
    store(db)

    record_decision(db, "acc-1", note="Founder was vague on the clinical data.")

    assert get_candidate(db, "acc-1").user_note == (
        "Founder was vague on the clinical data."
    )


def test_the_analysts_verdict_wins(db) -> None:
    store(db, verdict="no_fit")

    updated = record_decision(db, "acc-1", verdict="fits")

    # Both are kept. The model's answer is still on the record.
    assert updated.verdict == "no_fit"
    assert updated.user_verdict == "fits"
    assert updated.effective_verdict == "fits"
    assert updated.overridden is True


def test_agreeing_with_the_model_is_not_an_override(db) -> None:
    store(db, verdict="fits")

    updated = record_decision(db, "acc-1", verdict="fits")

    # Confirming is a decision, but it is not a disagreement.
    assert updated.overridden is False
    assert updated.decided_at is not None


def test_a_verdict_the_analyst_set_survives_a_rejudge(db) -> None:
    # The whole reason the human call lives in its own column. rejudge.py
    # rewrites `verdict`; it must not touch what a person decided.
    store(db, verdict="no_fit")
    record_decision(db, "acc-1", verdict="fits", note="Worth another look.")

    # A rejudge: same row saved again with a different model verdict.
    store(db, verdict="unknown")

    after = get_candidate(db, "acc-1")

    assert after.verdict == "unknown"
    assert after.user_verdict == "fits"
    assert after.user_note == "Worth another look."
    assert after.effective_verdict == "fits"


def test_a_note_and_a_verdict_save_independently(db) -> None:
    store(db)

    record_decision(db, "acc-1", note="Spoke to them at a conference.")
    record_decision(db, "acc-1", verdict="maybe")

    after = get_candidate(db, "acc-1")

    # Saving the verdict must not wipe the note written a moment earlier.
    assert after.user_note == "Spoke to them at a conference."
    assert after.user_verdict == "maybe"


def test_an_emptied_note_is_removed_rather_than_stored_blank(db) -> None:
    store(db)
    record_decision(db, "acc-1", note="Draft thought.")

    record_decision(db, "acc-1", note="   ")

    # None, not "", so "is there a note?" is one check everywhere.
    assert get_candidate(db, "acc-1").user_note is None


def test_clearing_hands_the_company_back_to_the_model(db) -> None:
    store(db, verdict="no_fit")
    record_decision(db, "acc-1", verdict="fits", note="Keep this.")

    cleared = clear_verdict(db, "acc-1")

    assert cleared.user_verdict is None
    assert cleared.effective_verdict == "no_fit"
    # Clearing the verdict is not clearing the note.
    assert cleared.user_note == "Keep this."


def test_filtering_uses_the_verdict_the_analyst_gave(db) -> None:
    store(db, accession="acc-1", name="Rescued Co", verdict="no_fit")
    store(db, accession="acc-2", name="Dropped Co", verdict="fits")

    record_decision(db, "acc-1", verdict="fits")
    record_decision(db, "acc-2", verdict="no_fit")

    fits = [c.company_name for c in list_candidates(db, verdicts=["fits"])]

    # The one the analyst rescued is a fit; the one they rejected is not.
    assert fits == ["Rescued Co"]


def test_disagreements_lists_only_real_overrides(db) -> None:
    store(db, accession="acc-1", name="Overruled Co", verdict="no_fit")
    store(db, accession="acc-2", name="Confirmed Co", verdict="fits")
    store(db, accession="acc-3", name="Untouched Co", verdict="maybe")

    record_decision(db, "acc-1", verdict="fits")
    record_decision(db, "acc-2", verdict="fits")
    record_decision(db, "acc-3", note="just a note, no verdict")

    names = [c.company_name for c in disagreements(db)]

    assert names == ["Overruled Co"]


def test_deciding_nothing_changes_nothing(db) -> None:
    store(db)

    unchanged = record_decision(db, "acc-1")

    assert unchanged.user_verdict is None
    assert unchanged.decided_at is None
