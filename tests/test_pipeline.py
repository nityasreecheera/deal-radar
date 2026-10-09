from contextlib import closing
from datetime import date
from pathlib import Path

import pytest

from src.candidates import find_by_company
from src.enrich import Enrichment
from src.judge import JudgementError
from src.edgar import SearchOutcome
from src.models import Candidate, FormDFiling
import src.pipeline as pipeline_module
from src.pipeline import default_window, run_radar
from src.seen import connect, count_seen, mark_seen, mark_seen_for_theme
from src.thesis import Thesis


def filing(name: str, amount: int | None = 4_000_000, **overrides) -> FormDFiling:
    data = {
        "accession": f"acc-{name}",
        "cik": "1",
        "company_name": name,
        "filed_date": "2026-07-28",
        "industry_group": "Other Health Care",
        "total_offering_amount": amount,
    }
    data.update(overrides)

    return FormDFiling(**data)


def thesis() -> Thesis:
    return Thesis.model_validate(
        {
            "domain": "Healthcare",
            "name": "Healthcare software",
            "description": "Software for clinical workflows.",
            "include": ["clinical software"],
            "filters": {"min_offering_amount": 500_000},
        }
    )


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    A company that fits has its funding history fetched from EDGAR.

    Left in place, every test that judges something "fits" made real requests
    and passed either way, because a failed history is only a problem line.
    """
    monkeypatch.setattr(pipeline_module, "fetch_history", lambda cik: [])


@pytest.fixture
def db(tmp_path: Path):
    with closing(connect(tmp_path / "radar.sqlite")) as connection:
        yield connection


def fetcher(
    filings: list[FormDFiling],
    problems: list[str] | None = None,
    unsearched: list[str] | None = None,
    searched: list[str] | None = None,
):
    def fetch(start: str, end: str):
        return SearchOutcome(
            filings,
            list(problems or []),
            list(unsearched or []),
            list(searched or ["Other Health Care"]),
        )

    return fetch


def verdict_judge(verdict: str = "fits", reason: str = "Clinical software."):
    def judge(f: FormDFiling, e: Enrichment, t: Thesis) -> Candidate:
        # Carries the enrichment onto the candidate, which is what the real
        # judge does. Without it the fixture quietly stored nothing, and a test
        # for reusing a stored lookup could never pass.
        return Candidate(
            filing=f,
            verdict=verdict,
            reason=reason,
            website=e.website,
            description=e.description,
        )

    return judge


def no_enrichment(f: FormDFiling) -> Enrichment:
    return Enrichment()


def test_default_window_covers_more_than_one_day() -> None:
    # A one-day window run on a Monday would miss the weekend's filings.
    start, end = default_window(days=3, today=date(2026, 7, 29))

    assert start == "2026-07-26"
    assert end == "2026-07-29"


def test_a_run_produces_candidates(db) -> None:
    run = run_radar(
        db,
        thesis(),
        "2026-07-26",
        "2026-07-29",
        fetch_filings=fetcher([filing("Acme Health, Inc.")]),
        enrich=no_enrichment,
        judge=verdict_judge(),
    )

    assert run.fetched == 1
    assert len(run.candidates) == 1
    assert len(run.interesting) == 1


def test_filtered_filings_are_reported_with_reasons(db) -> None:
    run = run_radar(
        db,
        thesis(),
        "2026-07-26",
        "2026-07-29",
        fetch_filings=fetcher(
            [filing("Acme Health, Inc."), filing("Tiny Co", amount=39)]
        ),
        enrich=no_enrichment,
        judge=verdict_judge(),
    )

    assert len(run.candidates) == 1
    assert [d.company_name for d in run.filtered_out] == ["Tiny Co"]
    assert "below" in run.filtered_out[0].reason


def test_a_known_company_is_not_surfaced_again(db) -> None:
    # Marked for this domain specifically. Novelty is per domain now: a company
    # another thesis looked at is still new to this one.
    mark_seen(db, "Acme Health, Inc.", source="form_d")
    mark_seen_for_theme(db, "Acme Health, Inc.", "Healthcare")

    run = run_radar(
        db,
        thesis(),
        "2026-07-26",
        "2026-07-29",
        fetch_filings=fetcher([filing("Acme Health, Inc.")]),
        enrich=no_enrichment,
        judge=verdict_judge(),
    )

    assert run.candidates == []
    assert run.already_seen == 1


def test_everything_judged_is_marked_including_a_rejection(db) -> None:
    # A no_fit company must be remembered, or it returns in every future digest.
    run = run_radar(
        db,
        thesis(),
        "2026-07-26",
        "2026-07-29",
        fetch_filings=fetcher([filing("Dental Group, Inc.")]),
        enrich=no_enrichment,
        judge=verdict_judge("no_fit", "A dental practice."),
    )

    assert run.interesting == []
    assert count_seen(db) == 1


def test_a_run_records_the_judgement_not_just_the_sighting(db) -> None:
    # The verdict used to exist only inside a rendered digest, so it was gone
    # the moment the message was sent.
    run_radar(
        db,
        thesis(),
        "2026-07-26",
        "2026-07-29",
        fetch_filings=fetcher([filing("Genomenon, Inc.")]),
        enrich=no_enrichment,
        judge=verdict_judge("fits", "AI software for genetic evidence."),
    )

    history = find_by_company(db, "Genomenon, Inc.")

    assert len(history) == 1
    assert history[0].verdict == "fits"
    assert history[0].reason == "AI software for genetic evidence."


def test_a_rejection_is_recorded_with_its_reason(db) -> None:
    # Knowing why something was rejected is the more valuable half.
    run_radar(
        db,
        thesis(),
        "2026-07-26",
        "2026-07-29",
        fetch_filings=fetcher([filing("Dental Group, Inc.")]),
        enrich=no_enrichment,
        judge=verdict_judge("no_fit", "A dental practice, not software."),
    )

    history = find_by_company(db, "Dental Group, Inc.")

    assert len(history) == 1
    assert history[0].verdict == "no_fit"
    assert "dental practice" in history[0].reason


def test_a_dry_run_records_no_judgement(db) -> None:
    run_radar(
        db,
        thesis(),
        "2026-07-26",
        "2026-07-29",
        fetch_filings=fetcher([filing("Genomenon, Inc.")]),
        enrich=no_enrichment,
        judge=verdict_judge(),
        mark=False,
    )

    assert find_by_company(db, "Genomenon, Inc.") == []


def test_a_dry_run_marks_nothing(db) -> None:
    # Marking is what makes a company old; doing it in a rehearsal would hide
    # the company from the next real digest.
    run = run_radar(
        db,
        thesis(),
        "2026-07-26",
        "2026-07-29",
        fetch_filings=fetcher([filing("Acme Health, Inc.")]),
        enrich=no_enrichment,
        judge=verdict_judge(),
        mark=False,
    )

    assert len(run.candidates) == 1
    assert count_seen(db) == 0


def test_a_failed_judgement_is_not_marked_as_seen(db) -> None:
    # Tomorrow's run should get another attempt rather than losing the company.
    def broken_judge(f, e, t):
        raise JudgementError("model returned nonsense")

    run = run_radar(
        db,
        thesis(),
        "2026-07-26",
        "2026-07-29",
        fetch_filings=fetcher([filing("Acme Health, Inc.")]),
        enrich=no_enrichment,
        judge=broken_judge,
    )

    assert run.candidates == []
    assert count_seen(db) == 0
    assert any("judgement failed" in problem for problem in run.problems)


def test_a_failed_enrichment_is_reported_and_the_run_continues(db) -> None:
    """
    Replaces a test that asserted the company was judged anyway.

    That was wrong, and stayed wrong until a search quota ran out and filed 33
    companies as unidentifiable in one morning. Judging on evidence that was
    never gathered records a finding nobody made — and marks the company seen,
    so the mistake is permanent. The run still continues; the company is simply
    left for tomorrow.
    """
    def broken_enrich(f):
        raise RuntimeError("search backend down")

    run = run_radar(
        db,
        thesis(),
        "2026-07-26",
        "2026-07-29",
        fetch_filings=fetcher(
            [filing("Acme Health, Inc."), filing("Other Co", accession="acc-2")]
        ),
        enrich=broken_enrich,
        judge=verdict_judge("maybe", "No information available."),
    )

    assert run.candidates == []
    assert len(run.problems) == 2


def test_interesting_puts_fits_before_maybe_and_drops_no_fit(db) -> None:
    def mixed_judge(f, e, t):
        table = {
            "Big Maybe": ("maybe", "Unclear."),
            "Small Fit": ("fits", "Clinical software."),
            "Rejected": ("no_fit", "A clinic."),
        }
        verdict, reason = table[f.company_name]

        return Candidate(filing=f, verdict=verdict, reason=reason)

    run = run_radar(
        db,
        thesis(),
        "2026-07-26",
        "2026-07-29",
        fetch_filings=fetcher(
            [
                filing("Big Maybe", amount=50_000_000),
                filing("Small Fit", amount=1_000_000),
                filing("Rejected", amount=9_000_000),
            ]
        ),
        enrich=no_enrichment,
        judge=mixed_judge,
    )

    names = [c.filing.company_name for c in run.interesting]

    # A fit beats a maybe regardless of how much larger the maybe's raise is.
    assert names == ["Small Fit", "Big Maybe"]


def test_larger_raises_sort_first_within_one_verdict(db) -> None:
    run = run_radar(
        db,
        thesis(),
        "2026-07-26",
        "2026-07-29",
        fetch_filings=fetcher(
            [filing("Smaller", amount=1_000_000), filing("Bigger", amount=9_000_000)]
        ),
        enrich=no_enrichment,
        judge=verdict_judge(),
    )

    assert [c.filing.company_name for c in run.interesting] == [
        "Bigger",
        "Smaller",
    ]


def test_limit_caps_how_many_are_judged(db) -> None:
    run = run_radar(
        db,
        thesis(),
        "2026-07-26",
        "2026-07-29",
        fetch_filings=fetcher([filing(f"Co {n}") for n in range(10)]),
        enrich=no_enrichment,
        judge=verdict_judge(),
        limit=3,
    )

    assert len(run.candidates) == 3


def test_skipped_count_combines_both_kinds_of_skip(db) -> None:
    mark_seen(db, "Known Co", source="form_d")
    mark_seen_for_theme(db, "Known Co", "Healthcare")

    run = run_radar(
        db,
        thesis(),
        "2026-07-26",
        "2026-07-29",
        fetch_filings=fetcher(
            [
                filing("Acme Health, Inc."),
                filing("Known Co"),
                filing("Tiny Co", amount=39),
            ]
        ),
        enrich=no_enrichment,
        judge=verdict_judge(),
    )

    # One already seen, one filtered out.
    assert run.already_seen == 1
    assert len(run.filtered_out) == 1
    assert run.skipped_count == 2


def test_fetch_problems_are_carried_through(db) -> None:
    run = run_radar(
        db,
        thesis(),
        "2026-07-26",
        "2026-07-29",
        fetch_filings=fetcher([], problems=["search 'Biotechnology': timeout"]),
        enrich=no_enrichment,
        judge=verdict_judge(),
    )

    assert run.problems == ["search 'Biotechnology': timeout"]


def test_another_domain_having_seen_a_company_does_not_hide_it(db) -> None:
    """
    The bug this exists for.

    The seen-index was keyed on the company alone, so whichever thesis ran
    first claimed a company forever. In practice the healthcare radar had
    already claimed 136 technology filings it rejected — exactly the companies
    a technology thesis is looking for — and every domain added after the first
    was quietly starved.
    """
    mark_seen(db, "Acme Health, Inc.", source="form_d")
    mark_seen_for_theme(db, "Acme Health, Inc.", "Healthcare")

    ai_tools = thesis()
    ai_tools.domain = "AI tools"

    run = run_radar(
        db,
        ai_tools,
        "2026-07-26",
        "2026-07-29",
        fetch_filings=fetcher([filing("Acme Health, Inc.")]),
        enrich=no_enrichment,
        judge=verdict_judge(),
    )

    # New to this domain, even though another one has already judged it.
    assert len(run.candidates) == 1
    assert run.already_seen == 0


def test_a_domain_does_not_see_the_same_company_twice(db) -> None:
    ai_tools = thesis()
    ai_tools.domain = "AI tools"

    for _ in range(2):
        run = run_radar(
            db,
            ai_tools,
            "2026-07-26",
            "2026-07-29",
            fetch_filings=fetcher([filing("Acme Health, Inc.")]),
            enrich=no_enrichment,
            judge=verdict_judge(),
        )

    # The second run finds nothing new: this domain has been offered it.
    assert run.candidates == []
    assert run.already_seen == 1


def test_a_lookup_another_domain_paid_for_is_reused(db) -> None:
    """
    Enrichment is the expensive step: a web search per company, on a free tier
    of about 500 a month. Without reuse, every extra domain re-runs it over the
    same companies and a second domain alone exhausts the quota.
    """
    lookups = 0

    def counting_enrich(f):
        nonlocal lookups
        lookups += 1
        return Enrichment(website="https://acme.com", description="Clinical software.")

    healthcare = thesis()

    run_radar(
        db,
        healthcare,
        "2026-07-26",
        "2026-07-29",
        fetch_filings=fetcher([filing("Acme Health, Inc.")]),
        enrich=counting_enrich,
        judge=verdict_judge(),
    )

    ai_tools = thesis()
    ai_tools.domain = "AI tools"

    run = run_radar(
        db,
        ai_tools,
        "2026-07-26",
        "2026-07-29",
        fetch_filings=fetcher([filing("Acme Health, Inc.")]),
        enrich=counting_enrich,
        judge=verdict_judge(),
    )

    # Judged again — fit is a question each thesis answers for itself — but the
    # evidence was recalled rather than re-fetched.
    assert len(run.candidates) == 1
    assert lookups == 1


def test_a_failed_lookup_is_not_recorded_as_a_finding(db) -> None:
    """
    "Unknown" means we looked and could not tell. When the lookup itself fails
    — a quota, a network error — judging on empty evidence records a finding
    nobody made, and marks the company seen so it is never retried. A search
    quota running out filed 33 companies as unidentifiable in one morning.
    """
    def broken_enrich(filing):
        raise RuntimeError("This request exceeds your plan's set usage limit")

    run = run_radar(
        db,
        thesis(),
        "2026-07-26",
        "2026-07-29",
        fetch_filings=fetcher([filing("Acme Health, Inc.")]),
        enrich=broken_enrich,
        judge=verdict_judge(),
    )

    assert run.candidates == []
    assert any("enrichment failed" in p for p in run.problems)
    # Not marked, so tomorrow tries again.
    assert count_seen(db) == 0


def test_a_lookup_that_finds_nothing_is_still_judged(db) -> None:
    # Different case: the search worked and returned nothing. That is a real
    # "we looked and could not tell", and belongs on the record.
    run = run_radar(
        db,
        thesis(),
        "2026-07-26",
        "2026-07-29",
        fetch_filings=fetcher([filing("Acme Health, Inc.")]),
        enrich=lambda f: Enrichment(),
        judge=verdict_judge(verdict="unknown", reason="No evidence."),
    )

    assert len(run.candidates) == 1
    assert count_seen(db) == 1
