"""
Domains a visitor writes for themselves, judged against companies already known.

A visitor to the public site can write a domain — what they are looking for and
what they would rule out — and see it judged. It appears in their own dropdown,
their own list and their own company pages, exactly like a real domain, and
nowhere else: not for other visitors, and never for the owner.

That separation is structural. Visitor domains and their judgements live in
tables of their own, keyed by an anonymous id the website keeps in a cookie. The
owner's connection never reads them. A visitor's connection reads them through
the same temporary views that hide the owner's private record (see
src/visibility.py), which is why a visitor's own domain shows up in every page
without any page knowing about it.

Two costs are bounded because a stranger is spending them:

- No web lookups. Only companies some public domain already looked up are used,
  with the description that lookup found.
- Judging is a model call per company, so each try judges a small batch, on a
  cheaper model than the owner's, with per-visitor and site-wide daily limits.

Which companies to judge is chosen before paying for anything, by how well each
company's own description matches the words the visitor used.
"""

from __future__ import annotations

import os
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field, field_validator

from src.candidates import StoredCandidate, list_candidates
from src.enrich import Enrichment
from src.judge import JudgeFunction, create_openai_compatible_judge, judge_filing
from src.models import Candidate, FormDFiling
from src.thesis import Thesis, ThesisFilters, apply_filters


# Companies judged per try. Each is a model call paid by the owner.
BATCH = int(os.getenv("VISITOR_BATCH", "15"))

# Tries one visitor may make in an hour, and all visitors together in a day.
TRIES_PER_HOUR = int(os.getenv("VISITOR_TRIES_PER_HOUR", "5"))
TRIES_PER_DAY = int(os.getenv("VISITOR_TRIES_PER_DAY", "50"))

MAX_DOMAINS = int(os.getenv("VISITOR_MAX_DOMAINS", "5"))
MAX_LINES = 8
MAX_LINE_LENGTH = 200

# Cheaper than the owner's model by an order of magnitude. A visitor is trying
# the tool, not running a fund on it.
VISITOR_MODEL = os.getenv("VISITOR_LLM_MODEL", "openai/gpt-4o-mini")

# Visitor data is a demo, not a record. Kept a month, then cleared.
KEEP_FOR = timedelta(days=30)

CONCURRENCY = 5

# Marked on every visitor domain, so one called "Healthcare" never mixes with
# the real Healthcare in a list, and the visitor can see which ones are theirs.
SUFFIX = " (yours)"

ID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

# Words in any sentence, which rank nothing.
COMMON = {
    "a", "an", "and", "any", "are", "as", "at", "be", "built", "building", "by",
    "companies", "company", "for", "from", "in", "is", "it", "its", "make",
    "makes", "making", "of", "on", "or", "run", "startups", "startup", "that",
    "the", "their", "them", "they", "this", "to", "up", "use", "uses", "using",
    "with", "who", "what", "which", "into", "than", "more", "less", "not", "no",
}


class VisitorError(ValueError):
    """Something a visitor asked for that cannot be done, worded for them."""


class VisitorLimit(VisitorError):
    """A try refused because a spending limit was reached."""


class VisitorDomainRequest(BaseModel):
    """What a visitor writes on the criteria page."""

    domain: str = Field(min_length=1, max_length=30)
    include: list[str] = Field(min_length=1, max_length=MAX_LINES)
    exclude: list[str] = Field(default_factory=list, max_length=MAX_LINES)
    min_amount: int | None = Field(default=None, ge=0)

    @field_validator("domain")
    @classmethod
    def plain_name(cls, value: str) -> str:
        value = value.strip()

        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 &+\-]{0,29}", value):
            raise ValueError("Use letters, numbers, spaces and hyphens for the name.")

        return value

    @field_validator("include", "exclude")
    @classmethod
    def tidy_lines(cls, lines: list[str]) -> list[str]:
        return [line.strip()[:MAX_LINE_LENGTH] for line in lines if line.strip()]

    @property
    def theme(self) -> str:
        return f"{self.domain}{SUFFIX}"

    def as_thesis(self) -> Thesis:
        return Thesis(
            domain=self.theme,
            name=self.domain,
            description=f"Companies matching: {'; '.join(self.include)}",
            include=self.include,
            exclude=self.exclude,
            filters=ThesisFilters(min_offering_amount=self.min_amount or 0),
            sec_industry_groups=[],
            public=False,
        )


class VisitorDomain(BaseModel):
    domain: str
    theme: str
    include: list[str]
    exclude: list[str] = Field(default_factory=list)
    min_amount: int | None = None
    judged: int = 0
    fits: int = 0
    maybe: int = 0
    left: int = 0


class TryResult(BaseModel):
    """What one batch did."""

    theme: str
    judged: int = 0
    fits: int = 0
    maybe: int = 0
    unknown: int = 0
    no_fit: int = 0
    left: int = 0
    problems: list[str] = Field(default_factory=list)


def valid_id(visitor_id: str | None) -> str | None:
    return visitor_id if visitor_id and ID_PATTERN.match(visitor_id) else None


# --- storage ---------------------------------------------------------------

def ensure_tables(connection: sqlite3.Connection) -> None:
    """
    Create the visitor tables, and keep visitor_candidate's columns in step
    with candidate's.

    visitor_candidate mirrors candidate column for column, plus the visitor, so
    a visitor's judgements can be read through the same views and the same
    queries as real ones. Columns added to candidate later are added here too.
    """
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS visitor_domain (
            visitor_id TEXT NOT NULL,
            theme      TEXT NOT NULL,
            request    TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (visitor_id, theme)
        );

        CREATE TABLE IF NOT EXISTS visitor_try (
            visitor_id TEXT NOT NULL,
            theme      TEXT NOT NULL,
            at         TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS visitor_candidate (
            visitor_id TEXT NOT NULL
        );
        """
    )

    candidate_columns = [
        row[1] for row in connection.execute("PRAGMA main.table_info(candidate)")
    ]
    present = {
        row[1] for row in connection.execute("PRAGMA main.table_info(visitor_candidate)")
    }

    for name in candidate_columns:
        if name not in present:
            connection.execute(f"ALTER TABLE visitor_candidate ADD COLUMN {name}")

    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_visitor_candidate_key "
        "ON visitor_candidate (visitor_id, accession, theme)"
    )
    connection.commit()


def forget_old(connection: sqlite3.Connection, now: datetime | None = None) -> None:
    """Clear visitor data older than a month."""
    cutoff = ((now or datetime.now(UTC)) - KEEP_FOR).isoformat()
    stale = [
        (row[0], row[1])
        for row in connection.execute(
            "SELECT visitor_id, theme FROM visitor_domain WHERE created_at < ?", (cutoff,)
        )
    ]

    for visitor_id, theme in stale:
        delete_domain(connection, visitor_id, theme)

    connection.execute("DELETE FROM visitor_try WHERE at < ?", (cutoff,))
    connection.commit()


def domains_for(connection: sqlite3.Connection, visitor_id: str) -> list[VisitorDomain]:
    rows = connection.execute(
        "SELECT theme, request FROM visitor_domain WHERE visitor_id = ? ORDER BY created_at",
        (visitor_id,),
    ).fetchall()

    found: list[VisitorDomain] = []

    for theme, raw in rows:
        request = VisitorDomainRequest.model_validate_json(raw)
        counts = dict(
            connection.execute(
                "SELECT verdict, COUNT(*) FROM visitor_candidate "
                "WHERE visitor_id = ? AND theme = ? GROUP BY verdict",
                (visitor_id, theme),
            ).fetchall()
        )
        found.append(
            VisitorDomain(
                domain=request.domain,
                theme=theme,
                include=request.include,
                exclude=request.exclude,
                min_amount=request.min_amount,
                judged=sum(counts.values()),
                fits=counts.get("fits", 0),
                maybe=counts.get("maybe", 0),
                left=len(pool(connection, visitor_id, request)),
            )
        )

    return found


def delete_domain(connection: sqlite3.Connection, visitor_id: str, theme: str) -> bool:
    deleted = connection.execute(
        "DELETE FROM visitor_domain WHERE visitor_id = ? AND theme = ?", (visitor_id, theme)
    ).rowcount
    connection.execute(
        "DELETE FROM visitor_candidate WHERE visitor_id = ? AND theme = ?", (visitor_id, theme)
    )
    connection.commit()

    return bool(deleted)


def check_allowance(connection: sqlite3.Connection, visitor_id: str, now: datetime | None = None) -> None:
    """Refuse a try past either limit, saying which and when it lifts."""
    now = now or datetime.now(UTC)
    hour = (now - timedelta(hours=1)).isoformat()
    day = (now - timedelta(days=1)).isoformat()

    mine = connection.execute(
        "SELECT COUNT(*) FROM visitor_try WHERE visitor_id = ? AND at > ?", (visitor_id, hour)
    ).fetchone()[0]

    if mine >= TRIES_PER_HOUR:
        raise VisitorLimit(
            f"That's {TRIES_PER_HOUR} tries this hour — the limit for one visitor. "
            "Try again in an hour."
        )

    everyone = connection.execute(
        "SELECT COUNT(*) FROM visitor_try WHERE at > ?", (day,)
    ).fetchone()[0]

    if everyone >= TRIES_PER_DAY:
        raise VisitorLimit(
            "The demo has reached today's limit for everyone. Try again tomorrow."
        )


# --- choosing what to judge --------------------------------------------------

def words(text: str) -> set[str]:
    """
    The words worth matching on.

    Two-letter words are kept: "AI", "EV" and "ML" are the most common things
    anyone types here, and dropping them was the old version's worst miss. A
    trailing "s" is trimmed so "batteries" finds "battery" and "centres" finds
    "centre"; crude, but it is ranking, not deciding.
    """
    found = set()

    for word in re.findall(r"[a-z0-9]{2,}", text.lower()):
        if word in COMMON:
            continue

        found.add(stem(word))

    return found


def stem(word: str) -> str:
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"

    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]

    return word


def relevance(row: StoredCandidate, wanted: set[str]) -> int:
    """How many of the visitor's words this company's own text contains, as words."""
    have = words(" ".join(part for part in (row.company_name, row.summary, row.description) if part))

    return len(wanted & have)


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
    """What the owner's lookup found. The description, never their verdict."""
    return Enrichment(
        website=row.website,
        description=row.description or row.summary,
        confident=bool(row.website),
    )


def public_themes(connection: sqlite3.Connection, private: list[str]) -> set[str]:
    return {
        row[0]
        for row in connection.execute("SELECT DISTINCT theme FROM main.candidate")
        if row[0] and row[0] not in private
    }


def pool(
    connection: sqlite3.Connection,
    visitor_id: str,
    request: VisitorDomainRequest,
    private: list[str] | None = None,
) -> list[StoredCandidate]:
    """
    Companies this visitor domain has not judged yet, best match first.

    Only companies a public domain has looked up — so nothing is searched for,
    and nothing a private domain alone found is shown to a stranger.
    """
    from src.visibility import private_domains

    hidden = private if private is not None else private_domains()
    allowed = public_themes(connection, hidden)
    done = {
        row[0]
        for row in connection.execute(
            "SELECT accession FROM visitor_candidate WHERE visitor_id = ? AND theme = ?",
            (visitor_id, request.theme),
        )
    }

    rows = [
        row
        for row in list_candidates(connection, limit=100_000)
        if row.theme in allowed and (row.description or row.summary)
    ]

    seen: set[str] = set()
    unique: list[StoredCandidate] = []

    for row in rows:
        if row.accession in seen or row.accession in done:
            continue

        seen.add(row.accession)
        unique.append(row)

    kept, _ = apply_filters([as_filing(row) for row in unique], request.as_thesis())
    keep = {filing.accession for filing in kept}
    unique = [row for row in unique if row.accession in keep]

    wanted = words(" ".join(request.include))

    # Stable, so among equals the newest filing — list order — comes first.
    unique.sort(key=lambda row: relevance(row, wanted), reverse=True)

    return unique


# --- judging -----------------------------------------------------------------

def save_judgement(
    connection: sqlite3.Connection,
    visitor_id: str,
    theme: str,
    accession: str,
    judged: Candidate,
) -> None:
    """
    Store a visitor's verdict as a copy of the company's facts with their answer.

    The facts — amounts, people, website, description — come from the owner's
    row for the same filing, because they are facts about the filing. The
    verdict, reason, summary and category are the visitor's thesis's own.
    Nothing the owner wrote about the company is copied.
    """
    from src.visibility import PRIVATE_COLUMNS

    columns = [
        row[1] for row in connection.execute("PRAGMA main.table_info(candidate)")
    ]
    overrides = {
        "theme": theme,
        "verdict": judged.verdict,
        "reason": judged.reason,
        "summary": judged.summary,
        "category": judged.category,
        "subdomain": judged.subdomain,
        "judged_at": datetime.now(UTC).isoformat(),
    }

    select = []
    params: list = [visitor_id]

    for name in columns:
        if name in overrides:
            select.append("?")
            params.append(overrides[name])
        elif name in PRIVATE_COLUMNS or name == "profile":
            select.append("NULL")
        else:
            select.append(name)

    params.append(accession)

    connection.execute(
        f"""
        INSERT OR REPLACE INTO visitor_candidate (visitor_id, {", ".join(columns)})
        SELECT ?, {", ".join(select)} FROM main.candidate
        WHERE accession = ? ORDER BY judged_at DESC LIMIT 1
        """,
        params,
    )


def judge_batch(
    connection: sqlite3.Connection,
    visitor_id: str,
    request: VisitorDomainRequest,
    judge: JudgeFunction | None = None,
    batch: int | None = None,
) -> TryResult:
    """Judge the next batch for one visitor domain, and record the try."""
    # Read at call time, so the limit is the one configured now.
    batch = batch or BATCH

    connection.execute(
        "INSERT INTO visitor_try (visitor_id, theme, at) VALUES (?, ?, ?)",
        (visitor_id, request.theme, datetime.now(UTC).isoformat()),
    )
    connection.commit()

    thesis = request.as_thesis()
    candidates = pool(connection, visitor_id, request)
    chosen = candidates[:batch]
    judger = judge or create_openai_compatible_judge(model=VISITOR_MODEL)

    def one(row: StoredCandidate):
        try:
            return row, judge_filing(as_filing(row), as_enrichment(row), thesis, judge=judger), ""
        except Exception as exc:  # noqa: BLE001 — any failure is a problem, not a verdict
            return row, None, str(exc)

    with ThreadPoolExecutor(max_workers=max(1, min(CONCURRENCY, len(chosen)))) as workers:
        results = list(workers.map(one, chosen))

    outcome = TryResult(theme=request.theme, left=len(candidates) - len(chosen))

    for row, judged, error in results:
        if judged is None:
            # Not stored, so it stays in the pool and the next try can have it.
            outcome.problems.append(f"{row.company_name}: {error}")
            outcome.left += 1
            continue

        save_judgement(connection, visitor_id, request.theme, row.accession, judged)
        outcome.judged += 1
        setattr(outcome, judged.verdict, getattr(outcome, judged.verdict) + 1)

    connection.commit()

    return outcome


def create_domain(
    connection: sqlite3.Connection,
    visitor_id: str,
    request: VisitorDomainRequest,
    judge: JudgeFunction | None = None,
) -> TryResult:
    """Save a visitor's domain and judge its first batch."""
    existing = connection.execute(
        "SELECT COUNT(*) FROM visitor_domain WHERE visitor_id = ?", (visitor_id,)
    ).fetchone()[0]

    if connection.execute(
        "SELECT 1 FROM visitor_domain WHERE visitor_id = ? AND theme = ?",
        (visitor_id, request.theme),
    ).fetchone():
        raise VisitorError(f"You already have a domain called {request.domain}.")

    if existing >= MAX_DOMAINS:
        raise VisitorError(
            f"You can keep {MAX_DOMAINS} domains at a time. Delete one to add another."
        )

    check_allowance(connection, visitor_id)

    connection.execute(
        "INSERT INTO visitor_domain (visitor_id, theme, request, created_at) VALUES (?, ?, ?, ?)",
        (visitor_id, request.theme, request.model_dump_json(), datetime.now(UTC).isoformat()),
    )
    connection.commit()

    return judge_batch(connection, visitor_id, request, judge=judge)


def judge_more(
    connection: sqlite3.Connection,
    visitor_id: str,
    theme: str,
    judge: JudgeFunction | None = None,
) -> TryResult:
    row = connection.execute(
        "SELECT request FROM visitor_domain WHERE visitor_id = ? AND theme = ?",
        (visitor_id, theme),
    ).fetchone()

    if row is None:
        raise VisitorError("That domain isn't one of yours.")

    check_allowance(connection, visitor_id)

    return judge_batch(connection, visitor_id, VisitorDomainRequest.model_validate_json(row[0]), judge=judge)
