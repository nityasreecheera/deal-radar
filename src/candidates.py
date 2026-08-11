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

from pydantic import BaseModel, Field, computed_field, field_validator

from src.models import Candidate, FitVerdict, RelatedPerson
from src.people import save_people


class StoredCandidate(BaseModel):
    """A judgement as it comes back out of the database."""

    accession: str = Field(min_length=1)
    canonical_name: str = Field(min_length=1)
    company_name: str = Field(min_length=1)
    verdict: FitVerdict
    reason: str = Field(min_length=1)
    summary: str | None = None
    category: str | None = None
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

    # The analyst's own call, overriding the model's. Null means they have not
    # disagreed — not that they agreed.
    user_verdict: FitVerdict | None = None
    user_note: str | None = None
    decided_at: str | None = None

    # Detail from the filing. Officers and directors are the most useful part:
    # a director based far from the company is often the investor's board seat.
    people: list[RelatedPerson] = Field(default_factory=list)
    amount_sold: int | None = None
    investor_count: int | None = None
    minimum_investment: int | None = None
    first_sale_date: str | None = None
    jurisdiction: str | None = None
    entity_type: str | None = None
    cik: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective_verdict(self) -> FitVerdict:
        """What this company counts as. The human's call wins."""
        return self.user_verdict or self.verdict

    @computed_field  # type: ignore[prop-decorator]
    @property
    def overridden(self) -> bool:
        """Whether the analyst disagreed with the model. Worth surfacing."""
        return self.user_verdict is not None and self.user_verdict != self.verdict

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
            summary, minimum_investment, first_sale_date, category
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?
        )
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
            summary         = COALESCE(excluded.summary, candidate.summary),
            minimum_investment = COALESCE(
                excluded.minimum_investment, candidate.minimum_investment
            ),
            first_sale_date = COALESCE(
                excluded.first_sale_date, candidate.first_sale_date
            ),
            category        = COALESCE(excluded.category, candidate.category)
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
            filing.minimum_investment,
            filing.first_sale_date,
            candidate.category,
        ),
    )
    connection.commit()

    # Also as rows, so "who else is this person on?" is a join rather than a
    # scan over every JSON blob in the table.
    save_people(connection, filing.accession, filing.related_persons)

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
        # COALESCE, not `verdict`, so a company the analyst re-labelled appears
        # under the label they gave it. Filtering on the model's answer would
        # make an override look like it had not been saved.
        placeholders = ", ".join("?" for _ in verdicts)
        clauses.append(f"COALESCE(user_verdict, verdict) IN ({placeholders})")
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


def record_decision(
    connection: sqlite3.Connection,
    accession: str,
    verdict: FitVerdict | None = None,
    note: str | None = None,
    decided_at: str | None = None,
) -> StoredCandidate | None:
    """
    Save the analyst's own call, their note, or both.

    The model's verdict is never touched. This writes alongside it, so a rejudge
    cannot wipe a human decision and disagreement stays visible.

    Passing None for a field leaves it as it was, which is what lets the note box
    and the verdict buttons save independently. Clearing is explicit: an empty
    note means "remove the note", and `clear_verdict` hands the company back to
    the model.
    """
    if verdict is None and note is None:
        return get_candidate(connection, accession)

    timestamp = decided_at or datetime.now(UTC).isoformat()

    sets: list[str] = []
    parameters: list[object] = []

    if verdict is not None:
        sets.append("user_verdict = ?")
        parameters.append(verdict)

    if note is not None:
        # An empty box means the note is gone, not that it is the empty string —
        # otherwise "is there a note?" needs two checks everywhere.
        cleaned = note.strip()
        sets.append("user_note = ?")
        parameters.append(cleaned or None)

    sets.append("decided_at = ?")
    parameters.append(timestamp)
    parameters.append(accession)

    connection.execute(
        f"UPDATE candidate SET {', '.join(sets)} WHERE accession = ?",
        parameters,
    )
    connection.commit()

    return get_candidate(connection, accession)


def clear_verdict(
    connection: sqlite3.Connection,
    accession: str,
) -> StoredCandidate | None:
    """
    Hand a company back to the model's judgement.

    Separate from record_decision because None already means "leave alone"
    there, and overloading it would make "no opinion" unreachable.
    """
    connection.execute(
        "UPDATE candidate SET user_verdict = NULL WHERE accession = ?",
        (accession,),
    )
    connection.commit()

    return get_candidate(connection, accession)


def disagreements(
    connection: sqlite3.Connection,
    theme: str | None = None,
) -> list[StoredCandidate]:
    """
    Every company where the analyst overruled the model.

    This is the measure of whether the thesis is working. A handful is healthy;
    a long list means the criteria in config/ do not say what the analyst
    actually means, and no amount of code fixes that.
    """
    query = [
        "SELECT * FROM candidate",
        "WHERE user_verdict IS NOT NULL AND user_verdict != verdict",
    ]
    parameters: list[object] = []

    if theme:
        query.append("AND theme = ?")
        parameters.append(theme)

    query.append("ORDER BY decided_at DESC")

    rows = connection.execute(" ".join(query), parameters).fetchall()

    return [StoredCandidate(**dict(row)) for row in rows]


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


class CategoryContext(BaseModel):
    """
    How many companies like this one you have already seen, and what you did.

    The point of the whole feature. One company tells you about one company;
    the count tells you whether a category is crowding up, or whether you keep
    rejecting the same thing and should say so in the thesis instead of paying
    to look each one up.
    """

    category: str
    seen: int = 0
    rejected: int = 0
    fitted: int = 0
    since: str = ""

    @property
    def is_worth_saying(self) -> bool:
        """
        Whether this is news.

        A count of one is just the company itself, and a count of two is a
        coincidence. Below three, saying it adds a line to the email without
        adding anything to know.
        """
        return self.seen >= 3 and self.category not in ("unclear", "")

    def describe(self) -> str:
        """One line for a human."""
        if not self.is_worth_saying:
            return ""

        ordinal = f"{self.seen}{ordinal_suffix(self.seen)}"
        sentence = f"The {ordinal} {self.category} company you've seen"

        if self.since:
            sentence += f" since {self.since}"

        if self.rejected and not self.fitted:
            # The actionable case: a category you keep turning down belongs in
            # the thesis file, not in the inbox.
            others = self.rejected - 1 if self.rejected == self.seen else self.rejected
            sentence += f" — you passed on {'the other ' if others else ''}{others}"
        elif self.fitted:
            sentence += f" — {self.fitted} of them fit"

        return sentence + "."


def ordinal_suffix(number: int) -> str:
    """1st, 2nd, 3rd, 4th. Teens are all 'th', which is the usual trap."""
    if 11 <= (number % 100) <= 13:
        return "th"

    return {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")


def category_context(
    connection: sqlite3.Connection,
    category: str | None,
    since: str | None = None,
    theme: str | None = None,
    accession: str | None = None,
) -> CategoryContext:
    """
    Count the companies in one category, and what was decided about them.

    Counts on the effective verdict, so a company the analyst personally rescued
    counts as a fit rather than as the model's rejection. Anything else would
    report your own history back to you wrongly.

    `accession` is included in the count rather than excluded: "the 5th" should
    count the one you are reading, which is what makes it an ordinal rather than
    a tally of everything else.
    """
    if not category:
        return CategoryContext(category="", since=since or "")

    clauses = ["category = ?"]
    parameters: list[object] = [category]

    if since:
        clauses.append("filed_date >= ?")
        parameters.append(since)

    if theme:
        clauses.append("theme = ?")
        parameters.append(theme)

    rows = connection.execute(
        "SELECT COALESCE(user_verdict, verdict) AS decided FROM candidate "
        f"WHERE {' AND '.join(clauses)}",
        parameters,
    ).fetchall()

    return CategoryContext(
        category=category,
        seen=len(rows),
        rejected=sum(1 for r in rows if r["decided"] == "no_fit"),
        fitted=sum(1 for r in rows if r["decided"] == "fits"),
        since=since or "",
    )


def category_counts(
    connection: sqlite3.Connection,
    since: str | None = None,
    theme: str | None = None,
) -> list[CategoryContext]:
    """Every category with at least one company, commonest first."""
    clauses = ["category IS NOT NULL", "category != ''"]
    parameters: list[object] = []

    if since:
        clauses.append("filed_date >= ?")
        parameters.append(since)

    if theme:
        clauses.append("theme = ?")
        parameters.append(theme)

    rows = connection.execute(
        """
        SELECT category,
               COUNT(*) AS seen,
               SUM(COALESCE(user_verdict, verdict) = 'no_fit') AS rejected,
               SUM(COALESCE(user_verdict, verdict) = 'fits') AS fitted
        FROM candidate
        WHERE """
        + " AND ".join(clauses)
        + " GROUP BY category ORDER BY seen DESC",
        parameters,
    ).fetchall()

    return [
        CategoryContext(
            category=row["category"],
            seen=row["seen"],
            rejected=row["rejected"] or 0,
            fitted=row["fitted"] or 0,
            since=since or "",
        )
        for row in rows
    ]


def quarter_start(on_date: str) -> str:
    """
    The first day of the quarter a date falls in.

    "This quarter" rather than "ever" because a category being busy now is the
    news. Four of something over two years is nothing; four in ten weeks is a
    pattern. An all-time count would just keep climbing and stop meaning
    anything.
    """
    year, month = int(on_date[:4]), int(on_date[5:7])

    return f"{year}-{3 * ((month - 1) // 3) + 1:02d}-01"


def describe_category(
    connection: sqlite3.Connection,
    candidate: Candidate,
    since: str | None = None,
    theme: str | None = None,
) -> str:
    """
    One line on how a company sits against the ones like it, or nothing.

    Returns an empty string below the threshold, which is most of the time and
    is correct: a category with two members has nothing to say, and a line
    saying so would be noise in a digest that only works while it stays short.
    """
    return category_context(
        connection,
        getattr(candidate, "category", None),
        since=since,
        theme=theme,
    ).describe()
