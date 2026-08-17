"""
HTTP API for the reading surface.

Read-mostly. The only writes are marking something as read, which is a fact about
the reader rather than about the research, so a browser cannot corrupt anything
the radar produced.
"""

from __future__ import annotations

import os
import time
from collections import deque
from contextlib import closing
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.candidates import (
    StoredCandidate,
    age_spread,
    category_context,
    category_counts,
    clear_verdict,
    count_by_verdict,
    count_unread,
    date_range,
    describe_rejection_clusters,
    disagreements,
    find_by_company,
    get_candidate,
    known_themes,
    list_candidates,
    mark_all_viewed,
    mark_viewed,
    domain_tallies,
    market_view,
    STEALTH_VIEW,
    quarter_start,
    record_decision,
    subdomain_counts,
    record_outreach,
    source_breakdown,
)
from src.chat import ChatAnswer, ChatError, answer_question
from src.funding import (
    FundingRound,
    describe_minimum,
    load_history,
    round_age,
    round_progress,
)
from src.contact import gmail_compose_url, gmail_search_url
from src.models import FitVerdict
from src.people import PersonLink, most_connected, shared_people
from src.seen import connect, count_seen
from src.thesis import (
    Thesis,
    ThesisError,
    available_themes,
    delete_thesis,
    load_all_theses,
    load_thesis,
    save_thesis,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIGEST_DIR = PROJECT_ROOT / "outputs" / "digests"

# The Next.js dev server is a different origin. Both are reached through an SSH
# tunnel to localhost, hence a specific list rather than a wildcard.
DEV_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]

app = FastAPI(
    title="Deal Radar",
    description=(
        "Newly visible companies you have not seen, and what was decided "
        "about them."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=DEV_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class Meta(BaseModel):
    """Everything the interface chrome needs, in one request."""

    companies_known: int = Field(ge=0)
    judgements: dict[str, int] = Field(default_factory=dict)
    unread: int = Field(ge=0)
    themes: list[str] = Field(default_factory=list)
    earliest_filing: str | None = None
    latest_filing: str | None = None
    thesis_name: str | None = None
    digest_dates: list[str] = Field(default_factory=list)


class CandidateList(BaseModel):
    """A filtered page of judgements."""

    count: int = Field(ge=0)
    unread: int = Field(ge=0)
    candidates: list[StoredCandidate] = Field(default_factory=list)


class CompanyDetail(BaseModel):
    """
    Everything worth knowing about one company, in one request.

    The judgement, its funding history, how far through the raise it was, and
    anyone on the filing who also turns up elsewhere. Assembled here rather than
    left to three round trips, because the page shows them together.
    """

    candidate: StoredCandidate
    rounds: list[FundingRound] = Field(default_factory=list)
    funding_summary: str = ""
    is_first_raise: bool = True
    total_raised: int = 0
    progress_percent: int | None = None
    progress_note: str = ""

    # How old the round was when it was filed. The filing date says when the
    # paperwork arrived; this says when money first moved, and the two can be a
    # year apart.
    days_open: int | None = None
    age_note: str = ""

    # Who the round is built for, from the smallest cheque it will accept.
    minimum_note: str | None = None

    # How this company sits against the others of its kind. Empty below the
    # threshold, which is most of the time.
    category: str | None = None
    category_note: str = ""

    # Links, not integrations. Compose opens Gmail with the address filled in;
    # search opens Gmail looking for anything already exchanged with the
    # company's domain. Neither reads a mailbox — the tool has no access to one.
    compose_url: str | None = None
    gmail_search_url: str | None = None

    shared_people: list[PersonLink] = Field(default_factory=list)


class MarkedRead(BaseModel):
    """How many were marked as read."""

    marked: int = Field(ge=0)


class DigestBody(BaseModel):
    """One saved digest, as it was sent."""

    date: str = Field(min_length=1)
    markdown: str


class Question(BaseModel):
    """A follow-up question about stored judgements."""

    question: str = Field(min_length=1, max_length=500)
    theme: str | None = None


class ErrorBody(BaseModel):
    ok: bool = False
    errors: list[str] = Field(default_factory=list)


# Every chat request costs money, and this can be published behind nothing more
# than a shared password. A cap turns a runaway — a stuck loop, a shared link, a
# bored visitor — into a refusal rather than a bill.
#
# Deliberately crude: in-memory, per-process, not per-user. It resets on restart
# and does not survive more than one worker. That is honest for a single-process
# deployment and should be replaced before it is relied on for anything else.
CHAT_LIMIT_PER_HOUR = int(os.getenv("CHAT_LIMIT_PER_HOUR", "60"))

_chat_times: deque[float] = deque()


def chat_allowance() -> tuple[bool, int]:
    """Whether another chat request is allowed, and how many remain."""
    now = time.monotonic()
    cutoff = now - 3600

    while _chat_times and _chat_times[0] < cutoff:
        _chat_times.popleft()

    remaining = CHAT_LIMIT_PER_HOUR - len(_chat_times)

    if remaining <= 0:
        return False, 0

    _chat_times.append(now)

    return True, remaining - 1


def digest_dates() -> list[str]:
    """Which digests exist on disk, newest first."""
    if not DIGEST_DIR.exists():
        return []

    return sorted(
        (path.stem for path in DIGEST_DIR.glob("*.md")),
        reverse=True,
    )


@app.get("/api/health")
def health() -> dict[str, bool]:
    """Liveness check."""
    return {"ok": True}


@app.get("/api/meta", response_model=Meta)
def get_meta() -> Meta:
    """
    Everything needed to draw the interface before any filtering.

    One request rather than five, because the theme dropdown, the calendar
    bounds and the unread badge are all needed at once on first paint.
    """
    try:
        thesis_name = load_thesis().name
    except ThesisError:
        # A missing or broken thesis file should not blank the whole interface.
        thesis_name = None

    # Configured domains and domains present in the data are both real. A
    # domain configured this morning has judged nothing yet, and omitting it
    # makes it look absent; a domain whose file was deleted still has history
    # worth filtering to.
    configured = available_themes()

    with closing(connect()) as connection:
        earliest, latest = date_range(connection)
        in_data = known_themes(connection)

        has_stealth = bool(
            list_candidates(connection, stealth=True, limit=1)
        )

        return Meta(
            companies_known=count_seen(connection),
            judgements=count_by_verdict(connection),
            unread=count_unread(connection),
            # Stealth last, and only when there is something in it. It is
            # not a thesis, so it belongs after the real ones rather than
            # sorted among them alphabetically.
            themes=sorted(set(configured) | set(in_data))
            + ([STEALTH_VIEW] if has_stealth else []),
            earliest_filing=earliest,
            latest_filing=latest,
            thesis_name=thesis_name,
            digest_dates=digest_dates(),
        )


@app.get("/api/candidates", response_model=CandidateList)
def get_candidates(
    verdict: list[str] | None = Query(default=None),
    theme: str | None = None,
    since: str | None = None,
    until: str | None = None,
    unread_only: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
) -> CandidateList:
    """
    Judgements, filtered. Every parameter is optional and combines.

    "Stealth" arrives as a theme because the interface has one dropdown, but it
    is not one: it is the companies no thesis could identify, narrowed to those
    whose shape says stealth rather than nothing. Translated here so no caller
    has to know the difference.
    """
    looking_for_stealth = theme == STEALTH_VIEW

    with closing(connect()) as connection:
        found = list_candidates(
            connection,
            verdicts=verdict,
            since=since,
            until=until,
            theme=None if looking_for_stealth else theme,
            unread_only=unread_only,
            limit=limit,
            stealth=looking_for_stealth,
        )

        return CandidateList(
            count=len(found),
            unread=count_unread(
                connection, theme=None if looking_for_stealth else theme
            ),
            candidates=found,
        )


@app.get(
    "/api/candidates/{accession}",
    response_model=StoredCandidate,
    responses={404: {"model": ErrorBody}},
)
def get_one(accession: str) -> StoredCandidate:
    """One judgement."""
    with closing(connect()) as connection:
        found = get_candidate(connection, accession)

    if found is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "errors": [f"no judgement for '{accession}'"]},
        )

    return found


@app.get(
    "/api/candidates/{accession}/detail",
    response_model=CompanyDetail,
    responses={404: {"model": ErrorBody}},
)
def get_detail(accession: str) -> CompanyDetail:
    """One company, with its history and connections."""
    with closing(connect()) as connection:
        found = get_candidate(connection, accession)

        if found is None:
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "errors": [f"no judgement for '{accession}'"]},
            )

        history = load_history(connection, found.cik) if found.cik else None
        percent, note = round_progress(found.offering_amount, found.amount_sold)

        days, age = round_age(found.first_sale_date, found.filed_date)

        context = category_context(
            connection,
            found.category,
            since=quarter_start(found.filed_date),
            theme=found.theme,
        )

        domain = None

        if found.website:
            from src.contact import registrable_domain

            domain = registrable_domain(found.website) or None

        return CompanyDetail(
            compose_url=(
                gmail_compose_url(
                    found.contact_email,
                    subject=f"{found.company_name} — Form D",
                )
                if found.contact_email
                else None
            ),
            gmail_search_url=(
                gmail_search_url(domain or found.company_name)
                if (domain or found.company_name)
                else None
            ),
            category=found.category,
            category_note=context.describe(),
            candidate=found,
            days_open=days,
            age_note=age,
            minimum_note=describe_minimum(found.minimum_investment),
            rounds=history.rounds if history else [],
            funding_summary=history.describe() if history else "",
            is_first_raise=history.is_first_time if history else True,
            total_raised=history.total_raised if history else 0,
            progress_percent=percent,
            progress_note=note,
            shared_people=shared_people(connection, accession),
        )


class CategoryRow(BaseModel):
    category: str
    seen: int = 0
    rejected: int = 0
    fitted: int = 0


class CategorySliceRow(BaseModel):
    category: str
    seen: int = 0
    fitted: int = 0


class SourceRow(BaseModel):
    industry_group: str
    seen: int = 0
    fitted: int = 0
    rejected: int = 0
    not_healthcare: int = 0
    breakdown: list[CategorySliceRow] = Field(default_factory=list)


class DealSizesRow(BaseModel):
    count: int = 0
    median: int | None = None
    lower_quartile: int | None = None
    upper_quartile: int | None = None
    smallest: int | None = None
    largest: int | None = None


class Market(BaseModel):
    """What the filings say about the market, rather than about the radar."""

    companies: int = 0
    excluded: int = 0
    deal_sizes: DealSizesRow = Field(default_factory=DealSizesRow)
    by_category: dict[str, DealSizesRow] = Field(default_factory=dict)
    company_age: dict[str, int] = Field(default_factory=dict)
    locations: list[dict] = Field(default_factory=list)


class DomainRow(BaseModel):
    domain: str
    judged: int = 0
    fitted: int = 0
    rejected: int = 0
    unknown: int = 0
    latest_filing: str | None = None
    typical_raise: int | None = None
    lower_quartile: int | None = None
    upper_quartile: int | None = None


class Analysis(BaseModel):
    """
    The whole picture, rather than one company at a time.

    Assembled in one response because the page shows them together and three
    round trips to draw one screen is three chances to render half a page.
    """

    judged: int = 0
    domains: list[DomainRow] = Field(default_factory=list)
    market: Market = Field(default_factory=Market)

    # How the selected domain divides up, by its own criteria rather than by a
    # global category list that suits whichever domain was written first.
    subdomains: list[dict] = Field(default_factory=list)
    categories: list[CategoryRow] = Field(default_factory=list)
    sources: list[SourceRow] = Field(default_factory=list)
    round_age: dict[str, int] = Field(default_factory=dict)
    overrides: list[StoredCandidate] = Field(default_factory=list)
    clusters: str = ""


class Outreach(BaseModel):
    """What a person wants recorded about contacting a company."""

    # Empty string clears it, so a mistaken click can be undone.
    status: str | None = None
    email: str | None = None


@app.post(
    "/api/candidates/{accession}/outreach",
    response_model=StoredCandidate,
    responses={404: {"model": ErrorBody}, 422: {"model": ErrorBody}},
)
def record_one_outreach(accession: str, outreach: Outreach) -> StoredCandidate:
    """
    Note that you contacted a company, or what came of it.

    Written by a person. Nothing here is inferred from a mailbox, because the
    tool has no access to one — so this records what someone chose to write
    down rather than guessing at what happened.
    """
    try:
        with closing(connect()) as connection:
            updated = record_outreach(
                connection,
                accession,
                status=outreach.status,
                email=outreach.email,
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"ok": False, "errors": [str(exc)]},
        ) from exc

    if updated is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "errors": [f"no judgement for '{accession}'"]},
        )

    return updated


class ThesisEdit(BaseModel):
    """A set of criteria as the browser sends it back."""

    thesis: Thesis

    # Which domain this replaces. Absent means a new one, and the difference
    # matters: without it, saving a thesis whose name already exists would
    # overwrite the other one instead of being refused.
    original_domain: str | None = None


@app.get("/api/theses", response_model=list[Thesis])
def list_theses() -> list[Thesis]:
    """Every set of criteria on disk."""
    return load_all_theses()


@app.put("/api/theses", response_model=Thesis, responses={422: {"model": ErrorBody}})
def write_thesis(edit: ThesisEdit) -> Thesis:
    """
    Create or replace a set of criteria.

    The body arrives as a Thesis, so anything malformed is rejected by
    validation before a file is touched. That is the point of the seam: the
    website can change what reaches an inbox, and cannot break the daily run
    by writing something the radar will fail to read tomorrow morning.
    """
    try:
        save_thesis(edit.thesis, original_domain=edit.original_domain)
    except ThesisError as exc:
        raise HTTPException(
            status_code=422,
            detail={"ok": False, "errors": [str(exc)]},
        ) from exc

    return edit.thesis


@app.delete("/api/theses/{domain}", responses={404: {"model": ErrorBody}})
def remove_thesis(domain: str) -> dict:
    """
    Delete a set of criteria.

    Judgements already made under it are kept. They record what was decided and
    when, and erasing them because the criteria changed would be rewriting
    history to tidy a menu.
    """
    if not delete_thesis(domain):
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "errors": [f"no criteria for {domain!r}"]},
        )

    with closing(connect()) as connection:
        kept = connection.execute(
            "SELECT COUNT(*) AS n FROM candidate WHERE theme = ?", (domain,)
        ).fetchone()["n"]

    return {"deleted": domain, "judgements_kept": kept}


@app.get("/api/analysis", response_model=Analysis)
def get_analysis(theme: str | None = None) -> Analysis:
    """
    Everything the analysis page shows.

    The source table is the one that pays for itself: the SEC industry group is
    the only thing known before a company costs anything to look up, so a group
    with no fits is a line you can delete from config/thesis.yaml.
    """
    with closing(connect()) as connection:
        judged = connection.execute(
            "SELECT COUNT(*) AS n FROM candidate"
            + (" WHERE theme = ?" if theme else ""),
            (theme,) if theme else (),
        ).fetchone()["n"]

        latest = connection.execute(
            "SELECT MAX(filed_date) AS d FROM candidate"
        ).fetchone()["d"]

        # The boxes currently being searched, so one that has produced nothing
        # still appears. An empty row is the finding.
        try:
            searched_groups = list(load_thesis().sec_industry_groups)
        except ThesisError:
            searched_groups = []

        seen = market_view(connection, theme=theme)

        try:
            configured = available_themes()
        except ThesisError:
            configured = []

        return Analysis(
            judged=judged,
            subdomains=subdomain_counts(connection, theme) if theme else [],
            domains=[
                DomainRow(**tally.model_dump())
                for tally in domain_tallies(connection, configured)
            ],
            market=Market(
                companies=seen.companies,
                excluded=seen.excluded,
                deal_sizes=DealSizesRow(**seen.deal_sizes.model_dump()),
                by_category={
                    name: DealSizesRow(**sizes.model_dump())
                    for name, sizes in seen.by_category.items()
                },
                company_age=seen.company_age,
                locations=seen.locations,
            ),
            categories=[
                CategoryRow(
                    category=c.category,
                    seen=c.seen,
                    rejected=c.rejected,
                    fitted=c.fitted,
                )
                for c in category_counts(connection, theme=theme)
            ],
            sources=[
                SourceRow(
                    industry_group=s.industry_group,
                    seen=s.seen,
                    fitted=s.fitted,
                    rejected=s.rejected,
                    not_healthcare=s.not_healthcare,
                    breakdown=[
                        CategorySliceRow(
                            category=slice_.category,
                            seen=slice_.seen,
                            fitted=slice_.fitted,
                        )
                        for slice_ in s.breakdown
                    ],
                )
                for s in source_breakdown(
                    connection, theme=theme, groups=searched_groups
                )
            ],
            round_age=age_spread(connection, theme=theme),
            overrides=disagreements(connection, theme=theme),
            clusters=describe_rejection_clusters(
                connection,
                since=quarter_start(latest) if latest else None,
                theme=theme,
            ),
        )


@app.get("/api/categories", response_model=list[dict])
def list_categories(
    since: str | None = None,
    theme: str | None = None,
) -> list[dict]:
    """
    What kinds of company you are actually seeing, commonest first.

    The rejection counts are the useful half. A category you have turned down
    four times belongs in config/thesis.yaml, where it costs nothing, rather
    than arriving every morning and being looked up at your expense.
    """
    with closing(connect()) as connection:
        return [
            {
                "category": c.category,
                "seen": c.seen,
                "rejected": c.rejected,
                "fitted": c.fitted,
            }
            for c in category_counts(connection, since=since, theme=theme)
        ]


@app.get("/api/people", response_model=list[dict])
def get_connected_people(limit: int = Query(default=20, ge=1, le=100)) -> list[dict]:
    """
    People appearing on more than one company we have seen.

    Only sees our own collection: EDGAR does not index the names on a Form D, so
    this cannot search all filings. It gets more useful as the database grows.
    """
    with closing(connect()) as connection:
        return [
            {"full_name": name, "companies": count}
            for name, count in most_connected(connection, limit=limit)
        ]


@app.get("/api/companies/{name}", response_model=list[StoredCandidate])
def company_history(name: str) -> list[StoredCandidate]:
    """
    Every judgement about one company, newest first.

    Matched through the same name normalisation as deduplication, so a filing
    under a slightly different legal name still resolves to the same history.
    """
    with closing(connect()) as connection:
        return find_by_company(connection, name)


@app.post(
    "/api/candidates/{accession}/viewed",
    response_model=StoredCandidate,
    responses={404: {"model": ErrorBody}},
)
def mark_one_viewed(accession: str) -> StoredCandidate:
    """
    Record that this one has been read.

    The only write in the API, and it records a fact about the reader rather than
    about the research.
    """
    with closing(connect()) as connection:
        updated = mark_viewed(connection, accession)

    if updated is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "errors": [f"no judgement for '{accession}'"]},
        )

    return updated


class Decision(BaseModel):
    """The analyst's own call on a company."""

    # Absent means "leave it alone", which is what lets the note box and the
    # verdict buttons save independently without clobbering each other.
    verdict: FitVerdict | None = None
    note: str | None = None

    # Explicit, because absent already means "no change" and there would
    # otherwise be no way back to the model's judgement.
    clear_verdict: bool = False


@app.post(
    "/api/candidates/{accession}/decision",
    response_model=StoredCandidate,
    responses={404: {"model": ErrorBody}},
)
def record_one_decision(accession: str, decision: Decision) -> StoredCandidate:
    """
    Save what the analyst thinks, overriding the model.

    The model's verdict is left exactly where it is. This writes alongside it, so
    rejudging cannot wipe a human decision and the two stay comparable.
    """
    with closing(connect()) as connection:
        if decision.clear_verdict:
            updated = clear_verdict(connection, accession)
        else:
            updated = None

        result = record_decision(
            connection,
            accession,
            verdict=decision.verdict,
            note=decision.note,
        )

        updated = result or updated

    if updated is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "errors": [f"no judgement for '{accession}'"]},
        )

    return updated


@app.get("/api/disagreements", response_model=list[StoredCandidate])
def list_disagreements(theme: str | None = None) -> list[StoredCandidate]:
    """
    Where the analyst overruled the model.

    A long list is a signal that the thesis file does not say what the analyst
    means, which is a config problem rather than a code one.
    """
    with closing(connect()) as connection:
        return disagreements(connection, theme=theme)


@app.post("/api/viewed", response_model=MarkedRead)
def mark_everything_viewed(theme: str | None = None) -> MarkedRead:
    """Mark everything unread as read, optionally within one theme."""
    with closing(connect()) as connection:
        return MarkedRead(marked=mark_all_viewed(connection, theme=theme))


@app.get("/api/digests", response_model=list[str])
def list_digests() -> list[str]:
    """Dates of saved digests, newest first."""
    return digest_dates()


@app.get(
    "/api/digests/{date}",
    response_model=DigestBody,
    responses={404: {"model": ErrorBody}},
)
def get_digest(date: str) -> DigestBody:
    """
    One saved digest.

    The date is used as a filename, so it is checked against the known list
    rather than trusted — a path fragment in a URL must never reach the
    filesystem unvalidated.
    """
    if date not in digest_dates():
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "errors": [f"no digest for '{date}'"]},
        )

    return DigestBody(
        date=date,
        markdown=(DIGEST_DIR / f"{date}.md").read_text(encoding="utf-8"),
    )


@app.post(
    "/api/chat",
    response_model=ChatAnswer,
    responses={
        400: {"model": ErrorBody},
        429: {"model": ErrorBody},
        503: {"model": ErrorBody},
    },
)
def ask(question: Question) -> ChatAnswer:
    """
    Answer a follow-up question from stored judgements only.

    No tools are available to the model, so it cannot search, act, or write. The
    context is chosen here in Python; that selection is the boundary.
    """
    allowed, remaining = chat_allowance()

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "ok": False,
                "errors": [
                    f"Too many questions — the limit is {CHAT_LIMIT_PER_HOUR} "
                    "an hour. Try again later."
                ],
            },
        )

    with closing(connect()) as connection:
        try:
            return answer_question(
                connection,
                question.question,
                theme=question.theme,
            )
        except ChatError as exc:
            message = str(exc)

            # An unconfigured or unreachable model is a service problem; a bad
            # question is the caller's.
            status = 503 if "key" in message.lower() else 400

            raise HTTPException(
                status_code=status,
                detail={"ok": False, "errors": [message]},
            ) from exc
