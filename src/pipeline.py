"""
The pipeline: fetch, filter, deduplicate, enrich, judge, record.

Ordering is the design. Free checks run before paid ones, and nothing is marked
as seen until it has actually been judged — a crash halfway through should not
cause a company to be silently skipped tomorrow.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, timedelta

from pydantic import BaseModel, Field

from src.candidates import save_candidate
from src.enrich import Enrichment, enrich_filing
from src.judge import JudgementError, judge_filing
from src.models import Candidate
from src.seen import filter_unseen, mark_seen
from src.thesis import Thesis, apply_filters


# Verdict order for display: the ones an analyst should read first.
VERDICT_ORDER = {"fits": 0, "maybe": 1, "no_fit": 2}


class DroppedFiling(BaseModel):
    """A filing removed before it cost anything, and why."""

    company_name: str
    reason: str


class RadarRun(BaseModel):
    """Everything one run of the radar did, including what it discarded."""

    start_date: str
    end_date: str
    generated_at: str

    fetched: int = 0
    filtered_out: list[DroppedFiling] = Field(default_factory=list)
    already_seen: int = 0
    candidates: list[Candidate] = Field(default_factory=list)
    problems: list[str] = Field(default_factory=list)

    @property
    def interesting(self) -> list[Candidate]:
        """Candidates worth an analyst's attention, best first."""
        return sorted(
            (c for c in self.candidates if c.verdict in ("fits", "maybe")),
            key=lambda c: (
                VERDICT_ORDER[c.verdict],
                -(c.filing.total_offering_amount or 0),
            ),
        )

    @property
    def skipped_count(self) -> int:
        """
        How much work the analyst did not have to do.

        This number is the product: everything the radar looked at so nobody
        else had to.
        """
        return self.already_seen + len(self.filtered_out)


def default_window(days: int = 1, today: date | None = None) -> tuple[str, str]:
    """
    The date range for a daily run.

    Form D is filed within fifteen days of a first sale and EDGAR publishes on
    business days, so a one-day window run on a Monday would miss the weekend.
    Overlapping windows are safe because deduplication is exact.
    """
    end = today or datetime.now(UTC).date()
    start = end - timedelta(days=days)

    return start.isoformat(), end.isoformat()


def run_radar(
    connection: sqlite3.Connection,
    thesis: Thesis,
    start_date: str,
    end_date: str,
    fetch_filings,
    enrich=enrich_filing,
    judge=judge_filing,
    mark: bool = True,
    limit: int | None = None,
) -> RadarRun:
    """
    Run the whole pipeline once.

    `mark` exists so a run can be rehearsed without consuming the novelty of
    every company it looks at. Marking is what makes a company old, and doing
    that during a test run would hide it from the next real digest.
    """
    generated_at = datetime.now(UTC).isoformat()

    filings, problems = fetch_filings(start_date, end_date)

    kept, dropped = apply_filters(filings, thesis)
    fresh, already_seen = filter_unseen(connection, kept)

    if limit is not None:
        fresh = fresh[:limit]

    candidates: list[Candidate] = []

    for filing in fresh:
        try:
            enrichment = enrich(filing)
        except Exception as exc:  # noqa: BLE001 - one bad lookup must not stop the run
            problems.append(f"{filing.company_name}: enrichment failed ({exc})")
            enrichment = Enrichment()

        try:
            candidate = judge(filing, enrichment, thesis)
        except (JudgementError, Exception) as exc:  # noqa: BLE001
            # An unjudged company is not marked as seen, so tomorrow's run gets
            # another attempt rather than losing it permanently.
            problems.append(f"{filing.company_name}: judgement failed ({exc})")
            continue

        candidates.append(candidate)

        if mark:
            # Everything judged is marked, including no_fit. Otherwise a company
            # that does not fit would resurface in every future digest.
            mark_seen(
                connection,
                filing.company_name,
                source="form_d",
                website=candidate.website,
                accession=filing.accession,
            )

            # And the judgement itself is kept, not just the fact of having
            # looked. Rendering a digest used to be the only place a verdict
            # existed, so it was gone as soon as the message was sent.
            #
            # The thesis name goes with it: the same company can fit one theme
            # and not another, so a verdict without its theme is ambiguous.
            save_candidate(connection, candidate, theme=thesis.name)

    return RadarRun(
        start_date=start_date,
        end_date=end_date,
        generated_at=generated_at,
        fetched=len(filings),
        filtered_out=[
            DroppedFiling(company_name=f.company_name, reason=r)
            for f, r in dropped
        ],
        already_seen=already_seen,
        candidates=candidates,
        problems=problems,
    )
