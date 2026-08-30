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
from src.funding import fetch_history, save_history
from src.enrich import Enrichment, enrich_filing
from src.judge import JudgementError, judge_filing
from src.models import Candidate
from src.seen import filter_unseen, mark_seen, mark_seen_for_theme
from src.thesis import Thesis, apply_filters


# Verdict order for display: the ones an analyst should read first.
VERDICT_ORDER = {"fits": 0, "maybe": 1, "unknown": 2, "no_fit": 3}


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

    # Industry groups EDGAR could not be asked about at all. Empty on a
    # healthy run. When it isn't, "nothing new" is not a finding.
    unsearched: list[str] = Field(default_factory=list)

    # Companies fetched and filtered but never judged, because the lookup or
    # the model failed. Same principle as `unsearched`: a morning where nothing
    # could be examined must not read like one where nothing was worth showing.
    unexamined: int = 0
    searched_count: int = 0

    @property
    def unknowns(self) -> list[Candidate]:
        """
        Companies nobody could establish anything about.

        Kept out of the digest and counted separately. These are a research task,
        not a judgement to read over coffee, and mixing them in was filling half
        the list with shrugs.
        """
        return [c for c in self.candidates if c.verdict == "unknown"]

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

    found = fetch_filings(start_date, end_date)
    filings, problems = found.filings, list(found.problems)

    kept, dropped = apply_filters(filings, thesis)
    # Novelty is per domain. A company the healthcare radar rejected is still
    # new to a technology radar, and treating it as old starves every domain
    # after the first.
    fresh, already_seen = filter_unseen(connection, kept, theme=thesis.domain)

    if limit is not None:
        fresh = fresh[:limit]

    candidates: list[Candidate] = []

    for filing in fresh:
        try:
            # A company another domain already looked up does not need looking
            # up again. Without this, every extra domain re-runs a web search
            # per company and a second one alone would exhaust the free tier.
            enrichment = recall_enrichment(connection, filing) or enrich(filing)
        except Exception as exc:  # noqa: BLE001 - one bad lookup must not stop the run
            # Skipped, not judged on nothing.
            #
            # Judging with empty evidence returns "unknown", which means "we
            # looked and could not tell" — and the company is then marked as
            # seen and never looked at again. When the lookup itself failed,
            # that records a finding we never made. A search quota running out
            # filed 33 companies as unidentifiable in one morning.
            #
            # An enrichment that returns nothing is different and still judged:
            # that is a real "we looked and found nothing".
            problems.append(f"{filing.company_name}: enrichment failed ({exc})")
            continue

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

            mark_seen_for_theme(connection, filing.company_name, thesis.domain)

            # And the judgement itself is kept, not just the fact of having
            # looked. Rendering a digest used to be the only place a verdict
            # existed, so it was gone as soon as the message was sent.
            #
            # The domain goes with it: the same company can fit one domain and
            # not another, so a verdict without it is ambiguous.
            save_candidate(connection, candidate, theme=thesis.domain)

            # Funding history, but only for companies worth reading about. It is
            # free, but it is still one request per filing, and there is no point
            # spending them on the rejections nobody opens.
            if candidate.verdict != "no_fit" and filing.cik:
                try:
                    save_history(connection, fetch_history(filing.cik))
                except Exception as exc:  # noqa: BLE001
                    problems.append(
                        f"{filing.company_name}: funding history failed ({exc})"
                    )

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
        unexamined=len(fresh) - len(candidates),
        unsearched=list(found.unsearched),
        searched_count=len(found.searched),
    )


def recall_enrichment(
    connection: sqlite3.Connection,
    filing,
) -> Enrichment | None:
    """
    What another domain already found out about this company.

    The judgement table keeps the website and description that enrichment
    produced, so a company examined for one thesis can be judged against another
    without paying for the lookup twice. The verdict is not reused — only the
    evidence — because fit is a question each thesis answers for itself.
    """
    row = connection.execute(
        """
        SELECT website, description FROM candidate
        WHERE canonical_name = ? AND description IS NOT NULL AND description != ''
        ORDER BY judged_at DESC LIMIT 1
        """,
        (filing.canonical_name,),
    ).fetchone()

    if row is None:
        return None

    return Enrichment(website=row["website"], description=row["description"])
