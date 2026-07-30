"""
HTTP API for the reading surface.

Read-mostly. The only writes are marking something as read, which is a fact about
the reader rather than about the research, so a browser cannot corrupt anything
the radar produced.
"""

from __future__ import annotations

from contextlib import closing
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.candidates import (
    StoredCandidate,
    count_by_verdict,
    count_unread,
    date_range,
    find_by_company,
    get_candidate,
    known_themes,
    list_candidates,
    mark_all_viewed,
    mark_viewed,
)
from src.chat import ChatAnswer, ChatError, answer_question
from src.seen import connect, count_seen
from src.thesis import ThesisError, load_thesis


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

    with closing(connect()) as connection:
        earliest, latest = date_range(connection)

        return Meta(
            companies_known=count_seen(connection),
            judgements=count_by_verdict(connection),
            unread=count_unread(connection),
            themes=known_themes(connection),
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
    """Judgements, filtered. Every parameter is optional and combines."""
    with closing(connect()) as connection:
        found = list_candidates(
            connection,
            verdicts=verdict,
            since=since,
            until=until,
            theme=theme,
            unread_only=unread_only,
            limit=limit,
        )

        return CandidateList(
            count=len(found),
            unread=count_unread(connection, theme=theme),
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
    responses={400: {"model": ErrorBody}, 503: {"model": ErrorBody}},
)
def ask(question: Question) -> ChatAnswer:
    """
    Answer a follow-up question from stored judgements only.

    No tools are available to the model, so it cannot search, act, or write. The
    context is chosen here in Python; that selection is the boundary.
    """
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
