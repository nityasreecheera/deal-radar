"""
The guest sandbox: someone else's criteria, run without showing them yours.

The tests that matter here are about what does not come back. A guest must not
be able to read a verdict the owner made, a reason the owner wrote, or a note
the owner left — those are the thesis, and the whole point of the sandbox is to
demonstrate the tool without handing over the strategy.
"""

import json
from contextlib import closing
from pathlib import Path

import pytest

from src.candidates import record_decision, save_candidate
from src.sandbox import MAX_JUDGED, SandboxRequest, keywords, pool, run
from src.seen import connect
from tests.test_candidates import candidate


@pytest.fixture
def db(tmp_path: Path):
    with closing(connect(tmp_path / "radar.sqlite")) as connection:
        yield connection


def a_judge(verdict: str = "fits", reason: str = "Matches the criteria."):
    """A judge that answers without a network or a bill."""
    def judge(system: str, prompt: str) -> str:
        return json.dumps(
            {
                "verdict": verdict,
                "reason": reason,
                "summary": "What the company does.",
                "category": "unclear",
            }
        )

    return judge


def request(**overrides) -> SandboxRequest:
    return SandboxRequest(
        **{"domain": "Guest", "include": ["cooling and energy"], **overrides}
    )


def stock(db, count: int = 3, **extra) -> None:
    for index in range(count):
        save_candidate(
            db,
            candidate(
                name=f"Company {index}",
                accession=f"acc-{index}",
                website=f"https://c{index}.example",
                description="They make things.",
                **extra,
            ),
            theme="Healthcare",
        )


def test_criteria_become_a_thesis() -> None:
    thesis = request(include=["batteries", "grid"], exclude=["oil"]).as_thesis()

    assert thesis.include == ["batteries", "grid"]
    assert thesis.exclude == ["oil"]


def test_a_run_judges_against_the_guests_criteria(db) -> None:
    stock(db, 2)

    outcome = run(db, request(), judge=a_judge())

    assert outcome.judged == 2
    assert [r.company_name for r in outcome.results] == ["Company 0", "Company 1"]


def test_the_owners_verdict_is_never_returned(db) -> None:
    """
    The company is judged again, from scratch, against the guest's criteria. The
    verdict already on record and the reason beside it are the strategy, and
    neither may leave the database.
    """
    save_candidate(
        db,
        candidate(
            name="Glacian",
            accession="a",
            verdict="fits",
            reason="OWNER REASONING — data centre cooling is explicitly in scope.",
            description="They make things.",
        ),
        theme="Energy",
    )

    outcome = run(db, request(), judge=a_judge(reason="Guest reasoning."))

    assert outcome.results[0].reason == "Guest reasoning."
    assert "OWNER REASONING" not in json.dumps(outcome.model_dump())


def test_the_owners_note_and_override_never_leave(db) -> None:
    save_candidate(db, candidate(accession="a", description="They make things."))
    record_decision(db, "a", verdict="no_fit", note="SECRET: passed, founder is difficult")

    outcome = run(db, request(), judge=a_judge())

    assert "SECRET" not in json.dumps(outcome.model_dump())


def test_the_owners_domain_names_never_leave(db) -> None:
    """Which domains the radar runs is itself a statement of strategy."""
    save_candidate(
        db, candidate(accession="a", description="They make things."), theme="Energy"
    )

    outcome = run(db, request(), judge=a_judge())

    assert "Energy" not in json.dumps(outcome.model_dump())


def test_a_run_is_capped(db) -> None:
    """Each judgement is a model call the owner pays for, not the guest."""
    stock(db, MAX_JUDGED + 6)

    outcome = run(db, request(), judge=a_judge())

    assert outcome.considered == MAX_JUDGED + 6
    assert outcome.judged == MAX_JUDGED


def test_the_same_company_is_not_judged_once_per_domain(db) -> None:
    """Five theses judged it; the guest should pay for one answer, not five."""
    for theme in ("Healthcare", "Energy", "Fintech", "AI tools", "AI infra"):
        save_candidate(
            db,
            candidate(name="Glacian", accession="a", description="They make things."),
            theme=theme,
        )

    outcome = run(db, request(), judge=a_judge())

    assert outcome.judged == 1


def test_companies_nobody_could_identify_are_not_paid_for(db) -> None:
    """With nothing to read, the answer is 'unknown' at full price."""
    save_candidate(db, candidate(accession="a", description=None, summary=None))

    assert pool(db, request()) == []


def test_a_size_filter_runs_before_the_model(db) -> None:
    save_candidate(db, candidate(accession="a", amount=200_000, description="x"))
    save_candidate(db, candidate(accession="b", amount=90_000_000, description="x"))

    outcome = run(db, request(max_amount=1_000_000), judge=a_judge())

    assert outcome.judged == 1


def test_a_company_that_could_not_be_judged_is_a_problem_not_a_rejection(db) -> None:
    """
    Reporting a failed call as 'did not match' would be a finding nobody made —
    the mistake this codebase keeps having to relearn.
    """
    stock(db, 1)

    def broken(system: str, prompt: str) -> str:
        return "not json at all"

    outcome = run(db, request(), judge=broken)

    assert outcome.judged == 0
    assert outcome.results == []
    assert len(outcome.problems) == 1


def test_only_matches_come_back(db) -> None:
    stock(db, 2)

    outcome = run(db, request(), judge=a_judge(verdict="no_fit"))

    assert outcome.judged == 2
    assert outcome.results == []


def test_the_pool_is_ranked_by_what_the_guest_asked_for(db) -> None:
    """
    Only a dozen of hundreds get judged, so which dozen decides whether the
    guest sees anything relevant at all. Judging the most recent regardless
    would show someone asking about cooling twelve unrelated businesses.
    """
    save_candidate(
        db,
        candidate(name="Irrelevant Corp", accession="a", filed_date="2026-08-30",
                  description="A dating app for cats."),
    )
    save_candidate(
        db,
        candidate(name="Glacian", accession="b", filed_date="2026-08-01",
                  description="Cooling optimisation for data centres."),
    )

    ranked = pool(db, request(include=["data centre cooling"]))

    assert ranked[0].company_name == "Glacian"


def test_common_words_do_not_rank_anything(db) -> None:
    from src.sandbox import keywords

    assert keywords(request(include=["software that makes data centres cheaper"])) == {
        "software", "data", "centres", "cheaper"
    }


def test_a_failure_in_one_company_does_not_lose_the_others(db) -> None:
    """Judged in parallel; one broken call must not take the run with it."""
    stock(db, 3)
    calls = {"n": 0}

    def flaky(system: str, prompt: str) -> str:
        calls["n"] += 1

        if calls["n"] == 2:
            raise RuntimeError("upstream fell over")

        return json.dumps(
            {"verdict": "fits", "reason": "ok", "summary": "s", "category": "unclear"}
        )

    outcome = run(db, request(), judge=flaky)

    assert outcome.judged == 2
    assert len(outcome.problems) == 1
