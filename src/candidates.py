"""
The record of what was decided, and why.

The seen-index answers "have I encountered this company?". This answers "what
did I conclude?" — which is the question that actually gets asked later, and the
one that used to be discarded the moment a digest was rendered.

Keyed on accession rather than company: a company can file more than once, and
each filing is a separate judgement made on separate evidence.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from src.models import Candidate, FitVerdict


class StoredCandidate(BaseModel):
    """A judgement as it comes back out of the database."""

    accession: str = Field(min_length=1)
    canonical_name: str = Field(min_length=1)
    company_name: str = Field(min_length=1)
    verdict: FitVerdict
    reason: str = Field(min_length=1)
    website: str | None = None
    description: str | None = None
    offering_amount: int | None = None
    filed_date: str = Field(min_length=1)
    industry_group: str | None = None
    city: str | None = None
    state: str | None = None
    incorporated: int | None = None
    judged_at: str = Field(min_length=1)


def save_candidate(
    connection: sqlite3.Connection,
    candidate: Candidate,
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
            industry_group, city, state, incorporated, judged_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (accession) DO UPDATE SET
            verdict         = excluded.verdict,
            reason          = excluded.reason,
            website         = COALESCE(excluded.website, candidate.website),
            description     = COALESCE(
                excluded.description, candidate.description
            ),
            judged_at       = excluded.judged_at
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
    limit: int | None = None,
) -> list[StoredCandidate]:
    """
    List judgements, newest filing first.

    `verdicts` and `since` are both optional filters. Parameters are bound rather
    than interpolated even though every caller is currently internal.
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

    if clauses:
        query.append("WHERE " + " AND ".join(clauses))

    query.append("ORDER BY filed_date DESC, offering_amount DESC")

    if limit is not None:
        query.append("LIMIT ?")
        parameters.append(limit)

    rows = connection.execute(" ".join(query), parameters).fetchall()

    return [StoredCandidate(**dict(row)) for row in rows]


def count_by_verdict(connection: sqlite3.Connection) -> dict[str, int]:
    """Tally judgements by verdict."""
    rows = connection.execute(
        "SELECT verdict, COUNT(*) AS n FROM candidate GROUP BY verdict"
    ).fetchall()

    return {row["verdict"]: int(row["n"]) for row in rows}


if __name__ == "__main__":
    from src.seen import connect

    with closing(connect()) as db:
        print("by verdict:", count_by_verdict(db))

        for item in list_candidates(db, verdicts=["fits"], limit=10):
            print(f"  {item.company_name} — {item.reason}")
