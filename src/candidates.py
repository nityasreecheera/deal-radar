"""
The record of what was decided, and why.

The seen-index answers "have I encountered this company?". This answers "what
did I conclude?" — which is the question that actually gets asked later, and the
one that used to be discarded the moment a digest was rendered.

Keyed on accession rather than company: a company can file more than once, and
each filing is a separate judgement made on separate evidence.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator

from src.models import Candidate, FitVerdict, RelatedPerson


class StoredCandidate(BaseModel):
    """A judgement as it comes back out of the database."""

    accession: str = Field(min_length=1)
    canonical_name: str = Field(min_length=1)
    company_name: str = Field(min_length=1)
    verdict: FitVerdict
    reason: str = Field(min_length=1)
    summary: str | None = None
    website: str | None = None
    description: str | None = None
    offering_amount: int | None = None
    filed_date: str = Field(min_length=1)
    industry_group: str | None = None
    city: str | None = None
    state: str | None = None
    incorporated: int | None = None
    judged_at: str = Field(min_length=1)

    # Which thesis reached this verdict. A verdict without it is ambiguous once
    # more than one theme exists.
    theme: str | None = None

    # Null means nobody has read it yet.
    viewed_at: str | None = None

    # Detail from the filing. Officers and directors are the most useful part:
    # a director based far from the company is often the investor's board seat.
    people: list[RelatedPerson] = Field(default_factory=list)
    amount_sold: int | None = None
    investor_count: int | None = None
    jurisdiction: str | None = None
    entity_type: str | None = None
    cik: str | None = None

    @field_validator("people", mode="before")
    @classmethod
    def parse_people(cls, value: object) -> object:
        """Accept the JSON string SQLite stores as well as a real list."""
        if value is None:
            return []

        if isinstance(value, str):
            if not value.strip():
                return []

            try:
                return json.loads(value)
            except json.JSONDecodeError:
                # A corrupt blob should cost the people list, not the record.
                return []

        return value

    @property
    def is_unread(self) -> bool:
        return self.viewed_at is None

    @property
    def filing_url(self) -> str | None:
        """Link to the filing on EDGAR, when the CIK is known."""
        if not self.cik:
            return None

        return (
            "https://www.sec.gov/Archives/edgar/data/"
            f"{int(self.cik)}/{self.accession.replace('-', '')}/primary_doc.xml"
        )


def save_candidate(
    connection: sqlite3.Connection,
    candidate: Candidate,
    theme: str | None = None,
    judged_at: str | None = None,
) -> StoredCandidate:
    """
    Record a judgement.

    Re-judging the same filing replaces the previous verdict, because a filing
    judged twice on better evidence should not leave a stale opinion behind. The
    original judged_at is not preserved for the same reason: what matters is the
    current conclusion and when it was reached.
    """
    filing = candidate.filing
    timestamp = judged_at or datetime.now(UTC).isoformat()

    connection.execute(
        """
        INSERT INTO candidate (
            accession, canonical_name, company_name, verdict, reason,
            website, description, offering_amount, filed_date,
            industry_group, city, state, incorporated, judged_at, theme,
            people, amount_sold, investor_count, jurisdiction, entity_type, cik,
            summary
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (accession) DO UPDATE SET
            verdict         = excluded.verdict,
            reason          = excluded.reason,
            website         = COALESCE(excluded.website, candidate.website),
            description     = COALESCE(
                excluded.description, candidate.description
            ),
            judged_at       = excluded.judged_at,
            theme           = COALESCE(excluded.theme, candidate.theme),
            people          = COALESCE(excluded.people, candidate.people),
            amount_sold     = COALESCE(
                excluded.amount_sold, candidate.amount_sold
            ),
            investor_count  = COALESCE(
                excluded.investor_count, candidate.investor_count
            ),
            jurisdiction    = COALESCE(
                excluded.jurisdiction, candidate.jurisdiction
            ),
            entity_type     = COALESCE(
                excluded.entity_type, candidate.entity_type
            ),
            cik             = COALESCE(excluded.cik, candidate.cik),
            summary         = COALESCE(excluded.summary, candidate.summary)
        """,
        (
            filing.accession,
            filing.canonical_name,
            filing.company_name,
            candidate.verdict,
            candidate.reason,
            candidate.website,
            candidate.description,
            filing.total_offering_amount,
            filing.filed_date,
            filing.industry_group,
            filing.city,
            filing.state,
            filing.year_of_incorporation,
            timestamp,
            theme,
            json.dumps([p.model_dump(mode="json") for p in filing.related_persons]),
            filing.total_amount_sold,
            filing.investor_count,
            filing.jurisdiction,
            filing.entity_type,
            filing.cik,
            candidate.summary,
        ),
    )
    connection.commit()

    stored = get_candidate(connection, filing.accession)

    if stored is None:  # pragma: no cover - the insert just succeeded
        raise RuntimeError(f"could not read back {filing.accession}")

    return stored


def get_candidate(
    connection: sqlite3.Connection,
    accession: str,
) -> StoredCandidate | None:
    """Fetch one judgement by filing."""
    row = connection.execute(
        "SELECT * FROM candidate WHERE accession = ?",
        (accession,),
    ).fetchone()

    return StoredCandidate(**dict(row)) if row is not None else None


def find_by_company(
    connection: sqlite3.Connection,
    company_name: str,
) -> list[StoredCandidate]:
    """
    Every judgement made about one company, newest first.

    Matched on the normalised name so that a company filing under a slightly
    different legal name still resolves to the same history.
    """
    from src.normalize import normalize_company_name

    canonical = normalize_company_name(company_name)

    if not canonical:
        return []

    rows = connection.execute(
        """
        SELECT * FROM candidate
        WHERE canonical_name = ?
        ORDER BY filed_date DESC, judged_at DESC
        """,
        (canonical,),
    ).fetchall()

    return [StoredCandidate(**dict(row)) for row in rows]


def list_candidates(
    connection: sqlite3.Connection,
    verdicts: list[str] | None = None,
    since: str | None = None,
    until: str | None = None,
    theme: str | None = None,
    unread_only: bool = False,
    limit: int | None = None,
) -> list[StoredCandidate]:
    """
    List judgements, newest filing first.

    Every filter is optional and combines with the others. Parameters are bound
    rather than interpolated, even though every caller is currently internal —
    `theme` comes from a dropdown and `since` from a date picker, and both will
    eventually arrive from a browser.
    """
    query = ["SELECT * FROM candidate"]
    clauses: list[str] = []
    parameters: list[object] = []

    if verdicts:
        placeholders = ", ".join("?" for _ in verdicts)
        clauses.append(f"verdict IN ({placeholders})")
        parameters.extend(verdicts)

    if since:
        clauses.append("filed_date >= ?")
        parameters.append(since)

    if until:
        clauses.append("filed_date <= ?")
        parameters.append(until)

    if theme:
        clauses.append("theme = ?")
        parameters.append(theme)

    if unread_only:
        clauses.append("viewed_at IS NULL")

    if clauses:
        query.append("WHERE " + " AND ".join(clauses))

    query.append("ORDER BY filed_date DESC, offering_amount DESC")

    if limit is not None:
        query.append("LIMIT ?")
        parameters.append(limit)

    rows = connection.execute(" ".join(query), parameters).fetchall()

    return [StoredCandidate(**dict(row)) for row in rows]


def mark_viewed(
    connection: sqlite3.Connection,
    accession: str,
    viewed_at: str | None = None,
) -> StoredCandidate | None:
    """
    Record that a human has read this one.

    The first reading is the one kept. Re-opening something does not make it
    newly read, and the interface only needs to know read from unread.
    """
    timestamp = viewed_at or datetime.now(UTC).isoformat()

    connection.execute(
        """
        UPDATE candidate
        SET viewed_at = COALESCE(viewed_at, ?)
        WHERE accession = ?
        """,
        (timestamp, accession),
    )
    connection.commit()

    return get_candidate(connection, accession)


def mark_all_viewed(
    connection: sqlite3.Connection,
    theme: str | None = None,
    viewed_at: str | None = None,
) -> int:
    """Mark everything unread as read. Returns how many changed."""
    timestamp = viewed_at or datetime.now(UTC).isoformat()

    parameters: list[object] = [timestamp]
    clause = "viewed_at IS NULL"

    if theme:
        clause += " AND theme = ?"
        parameters.append(theme)

    cursor = connection.execute(
        f"UPDATE candidate SET viewed_at = ? WHERE {clause}",
        parameters,
    )
    connection.commit()

    return cursor.rowcount


def count_by_verdict(connection: sqlite3.Connection) -> dict[str, int]:
    """Tally judgements by verdict."""
    rows = connection.execute(
        "SELECT verdict, COUNT(*) AS n FROM candidate GROUP BY verdict"
    ).fetchall()

    return {row["verdict"]: int(row["n"]) for row in rows}


def count_unread(
    connection: sqlite3.Connection,
    theme: str | None = None,
) -> int:
    """How many judgements nobody has read — the inbox badge."""
    if theme:
        row = connection.execute(
            "SELECT COUNT(*) AS n FROM candidate "
            "WHERE viewed_at IS NULL AND theme = ?",
            (theme,),
        ).fetchone()
    else:
        row = connection.execute(
            "SELECT COUNT(*) AS n FROM candidate WHERE viewed_at IS NULL"
        ).fetchone()

    return int(row["n"])


def known_themes(connection: sqlite3.Connection) -> list[str]:
    """
    Which themes appear in stored judgements.

    Read from the data rather than from config, so the dropdown reflects what
    actually exists rather than what is configured but never run.
    """
    rows = connection.execute(
        "SELECT DISTINCT theme FROM candidate "
        "WHERE theme IS NOT NULL AND theme != '' ORDER BY theme"
    ).fetchall()

    return [row["theme"] for row in rows]


def date_range(connection: sqlite3.Connection) -> tuple[str | None, str | None]:
    """
    Earliest and latest filing dates on record.

    The date picker needs bounds; offering a calendar over years with no data
    is a way of implying coverage that does not exist.
    """
    row = connection.execute(
        "SELECT MIN(filed_date) AS lo, MAX(filed_date) AS hi FROM candidate"
    ).fetchone()

    return row["lo"], row["hi"]


if __name__ == "__main__":
    from src.seen import connect

    with closing(connect()) as db:
        print("by verdict:", count_by_verdict(db))

        for item in list_candidates(db, verdicts=["fits"], limit=10):
            print(f"  {item.company_name} — {item.reason}")
