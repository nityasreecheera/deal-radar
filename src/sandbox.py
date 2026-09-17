"""
Running someone else's criteria, without showing them yours.

A guest shown the radar sees the judgements — and the judgements are the
strategy. What was looked at, what was kept, and above all the reason written
beside each one is the whole thesis, reconstructable in an afternoon by anyone
who scrolls.

So a guest gets the other half instead: they write their own criteria and the
radar runs against the same filings. They see what the tool does without seeing
what it concluded for anybody else. The companies are public SEC filings and the
descriptions are public web pages; neither was ever the secret.

Two costs to bound, because a stranger is spending them. Enrichment is already
paid for — these companies were looked up once and the description kept — so a
run costs only the judging, and that is capped per run and rate limited per
session. The cheap filters run first and the model only sees what survives,
which is the same shape as the real pipeline.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel, Field

from src.candidates import StoredCandidate, list_candidates
from src.enrich import Enrichment
from src.judge import JudgeFunction, JudgementError, judge_filing
from src.models import Candidate, FormDFiling
from src.thesis import Thesis, ThesisFilters


# How many companies one run may judge. Each is a model call paid for by the
# person who owns the radar, not the guest running the search, so this is a
# spending limit before it is anything else.
MAX_JUDGED = 12

# How many enriched companies to consider before judging. Larger than MAX_JUDGED
# so the cheap filters have something to narrow.
POOL_SIZE = 400

MAX_CRITERIA = 8
MAX_FIELD_LENGTH = 200

# Judged in parallel. Twelve sequential model calls take long enough that the
# proxy in front of this gives up before the answer arrives, and the guest sees
# a failure for a run that was working.
CONCURRENCY = 6

# Words that appear in any sentence and so rank nothing. Without them "software
# that makes data centres cheaper to run" would score every row that says "to".
COMMON = {
    "a", "an", "and", "any", "are", "as", "at", "be", "built", "building", "by",
    "companies", "company", "for", "from", "in", "is", "it", "its", "make",
    "makes", "making", "of", "on", "or", "run", "startups", "that", "the",
    "their", "them", "they", "this", "to", "up", "use", "uses", "using", "with",
}


class SandboxRequest(BaseModel):
    """Criteria typed by someone who is not the owner."""

    domain: str = Field(min_length=1, max_length=40)
    include: list[str] = Field(min_length=1, max_length=MAX_CRITERIA)
    exclude: list[str] = Field(default_factory=list, max_length=MAX_CRITERIA)
    min_amount: int | None = Field(default=None, ge=0)
    max_amount: int | None = Field(default=None, ge=0)

    def as_thesis(self) -> Thesis:
        return Thesis(
            domain=self.domain[:40],
            name=self.domain[:40],
            description=f"Companies matching: {'; '.join(self.include)}",
            include=[line[:MAX_FIELD_LENGTH] for line in self.include if line.strip()],
            exclude=[line[:MAX_FIELD_LENGTH] for line in self.exclude if line.strip()],
            filters=ThesisFilters(min_offering_amount=self.min_amount or 0),
            sec_industry_groups=[],
        )


class SandboxResult(BaseModel):
    """One company, judged against the guest's criteria and nobody else's."""

    company_name: str
    verdict: str
    reason: str
    summary: str | None = None
    website: str | None = None
    offering_amount: int | None = None
    filed_date: str
    city: str | None = None
    state: str | None = None


class SandboxRun(BaseModel):
    considered: int = 0
    judged: int = 0
    results: list[SandboxResult] = Field(default_factory=list)
    problems: list[str] = Field(default_factory=list)


def as_filing(row: StoredCandidate) -> FormDFiling:
    return FormDFiling(
        accession=row.accession,
        cik=row.cik or "0",
        company_name=row.company_name,
        filed_date=row.filed_date,
        industry_group=row.industry_group or "Other",
        city=row.city,
        state=row.state,
        entity_type=row.entity_type,
        jurisdiction=row.jurisdiction,
        year_of_incorporation=row.incorporated,
        total_offering_amount=row.offering_amount,
        total_amount_sold=row.amount_sold,
    )


def as_enrichment(row: StoredCandidate) -> Enrichment:
    """
    What was already found out about the company.

    `summary` is used when no scraped description survives. It describes the
    company rather than the owner's opinion of it, so it carries nothing about
    the thesis that produced it.
    """
    return Enrichment(
        website=row.website,
        description=row.description or row.summary,
        confident=bool(row.website),
    )


def keywords(request: SandboxRequest) -> set[str]:
    """The words worth matching on, taken from what the guest asked for."""
    text = " ".join(request.include).lower()

    return {
        word
        for word in re.findall(r"[a-z]{3,}", text)
        if word not in COMMON
    }


def relevance(row: StoredCandidate, wanted: set[str]) -> int:
    """How many of the guest's words this company's own text mentions."""
    if not wanted:
        return 0

    haystack = " ".join(
        part.lower()
        for part in (row.company_name, row.summary, row.description)
        if part
    )

    return sum(1 for word in wanted if word in haystack)


def pool(connection, request: SandboxRequest) -> list[StoredCandidate]:
    """
    The companies worth paying to judge, chosen without paying anything.

    Ordered by how well each one's own description matches the words the guest
    used. Without this the run judges whatever filed most recently, which for a
    dozen calls out of hundreds of companies means a guest asking about cooling
    is shown twelve unrelated businesses and concludes the tool does not work.
    The ranking costs nothing and the model still makes every actual decision.

    Deduplicated by filing: the same company appears once per thesis that judged
    it, and judging it five times would buy the same answer five times.
    """
    rows = list_candidates(
        connection,
        min_amount=request.min_amount,
        max_amount=request.max_amount,
        limit=POOL_SIZE,
    )

    wanted = keywords(request)
    seen: set[str] = set()
    unique: list[StoredCandidate] = []

    for row in rows:
        if row.accession in seen:
            continue

        # Nothing was ever found out about this one, so there is nothing for a
        # model to judge and the answer would be "unknown" at full price.
        if not (row.description or row.summary):
            continue

        seen.add(row.accession)
        unique.append(row)

    # Stable within a score, so the newest of two equally relevant companies
    # comes first — list_candidates already ordered by date.
    unique.sort(key=lambda row: relevance(row, wanted), reverse=True)

    return unique


def run(
    connection,
    request: SandboxRequest,
    judge: JudgeFunction | None = None,
    limit: int = MAX_JUDGED,
) -> SandboxRun:
    """Judge a capped set of companies against criteria the guest wrote."""
    thesis = request.as_thesis()
    candidates = pool(connection, request)
    outcome = SandboxRun(considered=len(candidates))
    chosen = candidates[:limit]

    def judge_one(row: StoredCandidate) -> tuple[StoredCandidate, Candidate | None, str]:
        try:
            return row, judge_filing(
                as_filing(row), as_enrichment(row), thesis, judge=judge
            ), ""
        except Exception as exc:  # noqa: BLE001 — any failure is a problem, not a verdict
            return row, None, str(exc)

    with ThreadPoolExecutor(max_workers=min(CONCURRENCY, max(1, len(chosen)))) as pool_:
        results = list(pool_.map(judge_one, chosen))

    for row, judged, error in results:
        if judged is None:
            # A company that could not be judged is reported as a problem, never
            # as a company that did not match. The difference is the one this
            # codebase keeps having to relearn.
            outcome.problems.append(f"{row.company_name}: {error}")
            continue

        outcome.judged += 1

        if judged.verdict in ("fits", "maybe"):
            outcome.results.append(
                SandboxResult(
                    company_name=row.company_name,
                    verdict=judged.verdict,
                    reason=judged.reason,
                    summary=judged.summary or row.summary,
                    website=row.website,
                    offering_amount=row.offering_amount,
                    filed_date=row.filed_date,
                    city=row.city,
                    state=row.state,
                )
            )

    return outcome
