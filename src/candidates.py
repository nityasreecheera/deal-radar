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
import statistics
from contextlib import closing
from datetime import UTC, datetime

from pydantic import BaseModel, Field, computed_field, field_validator

from src.models import Candidate, FitVerdict, RelatedPerson
from src.people import save_people


# What a free-text search looks in. Deliberately the fields a person can see on
# the page: searching a column the interface never shows would return rows with
# no visible reason for matching.
SEARCHED_FIELDS = (
    "company_name",
    "summary",
    "reason",
    "description",
    "city",
    "website",
)


def escape_like(text: str) -> str:
    """
    Make a typed word safe to put inside a LIKE pattern.

    `%` and `_` are wildcards in LIKE, so a search for "50_50" would otherwise
    match "5000" and a search for "%" would match every row. The backslash is
    escaped first, or it would escape the escapes.
    """
    for character in ("\\", "%", "_"):
        text = text.replace(character, "\\" + character)

    return text


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
    profile: str | None = None
    decided_at: str | None = None

    # Detail from the filing. Officers and directors are the most useful part:
    # a director based far from the company is often the investor's board seat.
    people: list[RelatedPerson] = Field(default_factory=list)
    amount_sold: int | None = None
    investor_count: int | None = None
    minimum_investment: int | None = None
    first_sale_date: str | None = None

    # Where to write, and whether you have. Set by hand, never by the radar.
    contact_email: str | None = None
    outreach_status: str | None = None
    outreach_at: str | None = None

    # Attached at read time, not stored on this row. Excluded from the API
    # schema of the candidate itself — the detail endpoint sends them once.
    researchers: list = Field(default_factory=list, exclude=True)
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
    def country(self) -> str | None:
        """The country, read from EDGAR's state or country code."""
        from src.regions import country_of

        return country_of(self.state)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def subdivision(self) -> str | None:
        """The state or province within that country, where there is one."""
        from src.regions import subdivision_of

        return subdivision_of(self.state)

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
            summary, minimum_investment, first_sale_date, category, subdomain
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?
        )
        ON CONFLICT (accession, theme) DO UPDATE SET
            verdict         = excluded.verdict,
            reason          = excluded.reason,
            website         = COALESCE(excluded.website, candidate.website),
            description     = COALESCE(
                excluded.description, candidate.description
            ),
            judged_at       = excluded.judged_at,
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
            category        = COALESCE(excluded.category, candidate.category),
            subdomain       = COALESCE(excluded.subdomain, candidate.subdomain)
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
            # Never null. SQLite treats nulls in a primary key as distinct, so a
            # judgement saved without a domain would insert a new row every time
            # instead of replacing the old one — a rejudge would pile up rather
            # than correct itself.
            theme or "",
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
            candidate.subdomain,
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
    theme: str | None = None,
) -> StoredCandidate | None:
    """
    Fetch one judgement by filing, and optionally by the domain that made it.

    One filing can now carry several judgements, because each thesis answers
    "does this fit" for itself and a company can be a fit for one domain and
    firmly not for another. Without a domain the most recent is returned, which
    is what a page showing a company in general wants.
    """
    if theme:
        row = connection.execute(
            "SELECT * FROM candidate WHERE accession = ? AND theme = ?",
            (accession, theme),
        ).fetchone()
    else:
        row = connection.execute(
            "SELECT * FROM candidate WHERE accession = ? "
            "ORDER BY judged_at DESC LIMIT 1",
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


# How a list can be ordered. Fixed strings, never built from a request.
SORTS = {
    "newest": "filed_date DESC, offering_amount DESC",
    "oldest": "filed_date ASC, offering_amount DESC",
    "largest": "offering_amount IS NULL, offering_amount DESC, filed_date DESC",
    "smallest": "offering_amount IS NULL, offering_amount ASC, filed_date DESC",
    "state": "state IS NULL OR state = '', state ASC, filed_date DESC",
}

# The names the first version used, still accepted so old links keep working.
SORTS["date"] = SORTS["newest"]
SORTS["amount"] = SORTS["largest"]


def list_candidates(
    connection: sqlite3.Connection,
    verdicts: list[str] | None = None,
    since: str | None = None,
    until: str | None = None,
    theme: str | None = None,
    unread_only: bool = False,
    query_text: str | None = None,
    min_amount: int | None = None,
    max_amount: int | None = None,
    limit: int | None = None,
    sort: str = "newest",
    states: list[str] | None = None,
) -> list[StoredCandidate]:
    """
    List judgements, newest filing first.

    Every filter is optional and combines with the others. Parameters are bound
    rather than interpolated, even though every caller is currently internal —
    `theme` comes from a dropdown and `since` from a date picker, and both will
    eventually arrive from a browser.

    `query_text` is free text typed by a person, and the only parameter here that
    is not chosen from a fixed set. It is matched with LIKE against the fields a
    person would expect to search — what the company is called, what it does, why
    it was judged that way, and where it is — and bound like everything else.
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

    # An undisclosed raise is excluded by a size filter rather than treated as
    # zero. "Under $1M" is a claim about the amount, and a filing that does not
    # state one cannot satisfy it.
    if min_amount is not None:
        clauses.append("offering_amount >= ?")
        parameters.append(min_amount)

    if max_amount is not None:
        clauses.append("offering_amount <= ?")
        parameters.append(max_amount)

    # Every word must appear somewhere, but not all in the same field: "cooling
    # data centre" should find a company whose summary says cooling and whose
    # reason says data centre. Matching the whole phrase against one column
    # would miss it, and matching any word would return most of the database.
    for word in (query_text or "").split():
        clauses.append(
            "("
            + " OR ".join(
                f"{field} LIKE ? ESCAPE '\\'"
                for field in SEARCHED_FIELDS
            )
            + ")"
        )
        parameters.extend([f"%{escape_like(word)}%"] * len(SEARCHED_FIELDS))

    if states:
        placeholders = ", ".join("?" for _ in states)
        clauses.append(f"state IN ({placeholders})")
        parameters.extend(states)

    if clauses:
        query.append("WHERE " + " AND ".join(clauses))

    # Sorted in SQL, before the limit, so "largest raise" means the largest of
    # everything that matches, not of whichever rows happened to load. Rows with
    # no amount or no state go last rather than first.
    query.append(f"ORDER BY {SORTS.get(sort, SORTS['newest'])}")

    if limit is not None:
        query.append("LIMIT ?")
        parameters.append(limit)

    rows = connection.execute(" ".join(query), parameters).fetchall()

    return [StoredCandidate(**dict(row)) for row in rows]


def save_profile(
    connection: sqlite3.Connection,
    accession: str,
    profile: str,
) -> None:
    """
    Keep a written explanation so it is paid for once.

    Written for every judgement of this filing, not just the one being read: the
    company is the same company whichever thesis judged it, and re-writing it per
    domain would buy the same paragraph five times.
    """
    connection.execute(
        "UPDATE candidate SET profile = ? WHERE accession = ?",
        (profile, accession),
    )
    connection.commit()


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

    # How many of these arrived in the same digest. Without it, three companies
    # of one kind landing together each get told they are "the 3rd", which is
    # true of none of them and reads as a bug — because it is one.
    arriving_now: int = 1

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

        # Several of a kind at once is a different observation from the Nth one
        # arriving alone, and a more interesting one.
        if self.arriving_now > 1:
            sentence = (
                f"{self.arriving_now} {self.category} companies in this digest"
            )

            earlier = self.seen - self.arriving_now

            if earlier > 0:
                sentence += f", making {self.seen}"

                if self.since:
                    sentence += f" since {self.since}"
            else:
                sentence += " — the first of these you've seen"

            return sentence + "."

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
    arriving_now: int = 1,
) -> str:
    """
    One line on how a company sits against the ones like it, or nothing.

    Returns an empty string below the threshold, which is most of the time and
    is correct: a category with two members has nothing to say, and a line
    saying so would be noise in a digest that only works while it stays short.
    """
    context = category_context(
        connection,
        getattr(candidate, "category", None),
        since=since,
        theme=theme,
    )
    context.arriving_now = arriving_now

    return context.describe()


def category_lines(
    connection: sqlite3.Connection,
    candidates: list[Candidate],
    since: str | None = None,
    theme: str | None = None,
) -> dict[str, str]:
    """
    A category line per company, said once per category.

    Repeating the same sentence under every company that shares a category
    fills a two-minute email with one observation restated. It goes to the
    first of them, and mentions how many arrived together.
    """
    grouped: dict[str, list[Candidate]] = {}

    for candidate in candidates:
        category = getattr(candidate, "category", None)

        if category:
            grouped.setdefault(category, []).append(candidate)

    lines: dict[str, str] = {}

    for members in grouped.values():
        line = describe_category(
            connection,
            members[0],
            since=since,
            theme=theme,
            arriving_now=len(members),
        )

        if line:
            lines[members[0].filing.accession] = line

    return lines


# Four is as many as a footer can carry before it stops being a footer. The
# categories are ranked by volume, so the ones that get cut are the small ones.
MAX_CLUSTERS_REPORTED = 4


def describe_rejection_clusters(
    connection: sqlite3.Connection,
    since: str | None = None,
    theme: str | None = None,
) -> str:
    """
    The kinds of company you keep turning down, for the bottom of the digest.

    This exists because the per-company line cannot do this job. That line only
    reaches companies that make the digest — fits and maybes — and those are the
    small categories. The big ones are all rejections, which by design never
    appear, so the pattern that is actually worth acting on was invisible in the
    one place it would be read.

    Only categories with no fits at all are listed. A category that has produced
    even one fit is not a rule you can write, and suggesting otherwise would be
    telling someone to filter out the thing they are looking for.
    """
    clusters = [
        c
        for c in category_counts(connection, since=since, theme=theme)
        if c.fitted == 0
        and c.seen >= 3
        and c.category not in ("unclear", "")
    ]

    if not clusters:
        return ""

    named = ", ".join(
        f"{c.seen} {c.category}" for c in clusters[:MAX_CLUSTERS_REPORTED]
    )

    total = sum(c.seen for c in clusters)

    return (
        f"This quarter: {named} — all passed. "
        f"That's {total} companies looked up to reject. Worth a thesis rule?"
    )


class CategorySlice(BaseModel):
    """One kind of business found inside one SEC industry group."""

    category: str
    seen: int = 0
    fitted: int = 0


class SourceBreakdown(BaseModel):
    """
    What one SEC industry group actually delivers, broken down by what the
    companies turn out to be.

    The most useful view in the product, because the industry group is the only
    thing known *before* a company is looked up. Everything else — what it does,
    whether it fits — costs a search and a model call to find out. Seeing that a
    box yields mostly drug companies, or mostly things that are not healthcare
    at all, is what tells you whether to keep searching it.
    """

    industry_group: str
    seen: int = 0
    fitted: int = 0
    rejected: int = 0
    not_healthcare: int = 0
    breakdown: list[CategorySlice] = Field(default_factory=list)

    @property
    def hit_rate(self) -> float:
        return (self.fitted / self.seen) if self.seen else 0.0


def source_breakdown(
    connection: sqlite3.Connection,
    theme: str | None = None,
    groups: list[str] | tuple[str, ...] | None = None,
) -> list[SourceBreakdown]:
    """
    Which SEC industry groups are earning their keep, and what comes out of each.

    `groups` is the list being searched. Passing it includes boxes that have
    produced nothing at all, which would otherwise be invisible — and a box
    being searched for weeks with zero results is exactly what someone needs to
    see.
    """
    clauses = ["industry_group IS NOT NULL"]
    parameters: list[object] = []

    if theme:
        clauses.append("theme = ?")
        parameters.append(theme)

    rows = connection.execute(
        """
        SELECT industry_group,
               COALESCE(category, 'unclear') AS category,
               COUNT(*) AS seen,
               SUM(COALESCE(user_verdict, verdict) = 'fits')   AS fitted,
               SUM(COALESCE(user_verdict, verdict) = 'no_fit') AS rejected
        FROM candidate
        WHERE """
        + " AND ".join(clauses)
        + " GROUP BY industry_group, category",
        parameters,
    ).fetchall()

    found: dict[str, SourceBreakdown] = {}

    for row in rows:
        source = found.setdefault(
            row["industry_group"],
            SourceBreakdown(industry_group=row["industry_group"]),
        )

        source.seen += row["seen"]
        source.fitted += row["fitted"] or 0
        source.rejected += row["rejected"] or 0

        if row["category"] == "not healthcare":
            source.not_healthcare += row["seen"]

        source.breakdown.append(
            CategorySlice(
                category=row["category"],
                seen=row["seen"],
                fitted=row["fitted"] or 0,
            )
        )

    # A searched box with nothing in it is a real finding, not an empty row.
    for group in groups or ():
        found.setdefault(group, SourceBreakdown(industry_group=group))

    for source in found.values():
        source.breakdown.sort(key=lambda slice_: -slice_.seen)

    return sorted(found.values(), key=lambda s: -s.seen)


def age_spread(connection: sqlite3.Connection, theme: str | None = None) -> dict:
    """
    How old rounds are by the time they reach you.

    Counts only rows with a first-sale date; the rest genuinely do not say. The
    buckets are coarse on purpose — the question is "is this fresh or has it
    been running for months", not the exact number of days.
    """
    clauses = ["first_sale_date IS NOT NULL"]
    parameters: list[object] = []

    if theme:
        clauses.append("theme = ?")
        parameters.append(theme)

    rows = connection.execute(
        "SELECT julianday(filed_date) - julianday(first_sale_date) AS days "
        "FROM candidate WHERE " + " AND ".join(clauses),
        parameters,
    ).fetchall()

    buckets = {
        "under 2 weeks": 0,
        "2 weeks to 3 months": 0,
        "3 to 12 months": 0,
        "over a year": 0,
    }

    for row in rows:
        days = row["days"]

        if days is None or days < 0:
            continue

        if days <= 14:
            buckets["under 2 weeks"] += 1
        elif days <= 90:
            buckets["2 weeks to 3 months"] += 1
        elif days <= 365:
            buckets["3 to 12 months"] += 1
        else:
            buckets["over a year"] += 1

    return buckets


# What can be recorded about reaching out. Deliberately short: this is a memory
# aid, not a CRM, and a longer list would invite pretending the pipeline is
# something it is not.
OUTREACH_STATUSES = ("emailed", "replied", "meeting", "passed")


def record_outreach(
    connection: sqlite3.Connection,
    accession: str,
    status: str | None = None,
    email: str | None = None,
    at: str | None = None,
) -> StoredCandidate | None:
    """
    Note that you contacted a company, or what came of it.

    Set by a person, never by the radar. Nothing here is inferred from a mailbox
    — the tool has no access to one — so this is an honest record of what
    someone chose to write down rather than a guess at what happened.

    Passing None leaves a field alone; an empty status clears it, so a mistaken
    click can be undone.
    """
    if status is None and email is None:
        return get_candidate(connection, accession)

    sets: list[str] = []
    parameters: list[object] = []

    if status is not None:
        cleaned = status.strip().lower()

        if cleaned and cleaned not in OUTREACH_STATUSES:
            raise ValueError(f"unknown outreach status: {status!r}")

        sets.append("outreach_status = ?")
        parameters.append(cleaned or None)

        sets.append("outreach_at = ?")
        parameters.append((at or datetime.now(UTC).isoformat()) if cleaned else None)

    if email is not None:
        sets.append("contact_email = ?")
        parameters.append(email.strip() or None)

    parameters.append(accession)

    connection.execute(
        f"UPDATE candidate SET {', '.join(sets)} WHERE accession = ?",
        parameters,
    )
    connection.commit()

    return get_candidate(connection, accession)


def save_contact_email(
    connection: sqlite3.Connection,
    accession: str,
    email: str | None,
) -> None:
    """Store an address found on a company's website."""
    connection.execute(
        "UPDATE candidate SET contact_email = ? WHERE accession = ?",
        (email, accession),
    )
    connection.commit()


# Below this a median is a coincidence rather than a benchmark. Eight is not a
# magic number; it is the point where quoting "the typical raise" stops feeling
# like a lie.
MIN_FOR_A_BENCHMARK = 8

# Categories that place a company outside the market being measured, or fail to
# place it at all. A median including things nobody could identify is not a
# benchmark for anything.
#
# "not healthcare" is a label the healthcare thesis produces; "other" is what the
# general vocabulary produces for the same situation. Both mean "this filing is
# not what we were looking for", which is exactly what a market benchmark has to
# leave out — whichever domain is being read.
NON_MARKET_CATEGORIES = ("not healthcare", "other", "unclear")


class DealSizes(BaseModel):
    """
    What a raise looks like in this market.

    The most useful thing on the page for someone doing the work rather than
    tuning the tool: when a company turns up raising $8m, "is that normal here"
    becomes a question with an answer.

    Robust to incomplete coverage in a way a trend line is not. A median over
    140 companies stays roughly a median even if a week of filings was missed;
    a month-over-month chart would show that missed week as a market downturn.
    """

    count: int = 0
    median: int | None = None
    lower_quartile: int | None = None
    upper_quartile: int | None = None
    smallest: int | None = None
    largest: int | None = None


def summarise_amounts(amounts: list[int]) -> DealSizes:
    """Quartiles from a list of raises, or empties when there are too few."""
    usable = sorted(a for a in amounts if a and a > 0)

    if len(usable) < MIN_FOR_A_BENCHMARK:
        return DealSizes(count=len(usable))

    quartiles = statistics.quantiles(usable, n=4)

    return DealSizes(
        count=len(usable),
        median=int(statistics.median(usable)),
        lower_quartile=int(quartiles[0]),
        upper_quartile=int(quartiles[2]),
        smallest=usable[0],
        largest=usable[-1],
    )


class MarketView(BaseModel):
    """The market as seen from the filings, rather than the radar's own health."""

    companies: int = 0

    # Filings left out because nobody could say what the company does, or it
    # turned out to be a different kind of business. Reported rather than
    # silently dropped: "based on 5 of 21" is a fact a reader deserves.
    excluded: int = 0
    deal_sizes: DealSizes = Field(default_factory=DealSizes)
    by_category: dict[str, DealSizes] = Field(default_factory=dict)
    company_age: dict[str, int] = Field(default_factory=dict)
    locations: list[dict] = Field(default_factory=list)


def market_view(
    connection: sqlite3.Connection,
    theme: str | None = None,
    this_year: int | None = None,
) -> MarketView:
    """
    What the filings say about the market, ignoring everything that is not it.

    Companies categorised "not healthcare" or "unclear" are excluded throughout.
    They are real filings and they cost real money to look up, but they are not
    part of the market anyone is trying to understand, and a median that
    includes an animation studio is not a healthcare benchmark.
    """
    clauses = [
        "category IS NOT NULL",
        f"category NOT IN ({', '.join('?' for _ in NON_MARKET_CATEGORIES)})",
    ]
    parameters: list[object] = list(NON_MARKET_CATEGORIES)

    if theme:
        clauses.append("theme = ?")
        parameters.append(theme)

    # One row per company, not per judgement.
    #
    # A company judged by three domains has three rows, and across all domains
    # it would land in the amounts list three times — quietly weighting the
    # median toward whatever companies happen to interest several theses at
    # once. Reading a single domain this never arose, so the bug only appeared
    # when the fifth domain did.
    rows = connection.execute(
        "SELECT category, offering_amount, state, incorporated, filed_date "
        "FROM candidate WHERE " + " AND ".join(clauses) + " "
        "GROUP BY canonical_name",
        parameters,
    ).fetchall()

    # How many were set aside, so the page can say what it is based on.
    counted = ["category IS NOT NULL"]
    counted_parameters: list[object] = []

    if theme:
        counted.append("theme = ?")
        counted_parameters.append(theme)

    everything = connection.execute(
        "SELECT COUNT(DISTINCT canonical_name) AS n FROM candidate WHERE "
        + " AND ".join(counted),
        counted_parameters,
    ).fetchone()["n"]

    if not rows:
        return MarketView(excluded=everything)

    year = this_year or int(max(r["filed_date"] for r in rows)[:4])

    per_category: dict[str, list[int]] = {}
    ages = {"founded this year": 0, "1 to 2 years": 0, "3 to 5 years": 0, "older": 0}
    places: dict[str, int] = {}

    for row in rows:
        if row["offering_amount"]:
            per_category.setdefault(row["category"], []).append(
                row["offering_amount"]
            )

        if row["incorporated"]:
            age = year - row["incorporated"]
            key = (
                "founded this year"
                if age <= 0
                else "1 to 2 years"
                if age <= 2
                else "3 to 5 years"
                if age <= 5
                else "older"
            )
            ages[key] += 1

        if row["state"]:
            places[row["state"]] = places.get(row["state"], 0) + 1

    every_amount = [a for amounts in per_category.values() for a in amounts]

    return MarketView(
        companies=len(rows),
        excluded=everything - len(rows),
        deal_sizes=summarise_amounts(every_amount),
        by_category={
            category: summarise_amounts(amounts)
            for category, amounts in per_category.items()
            if len(amounts) >= MIN_FOR_A_BENCHMARK
        },
        company_age=ages,
        locations=[
            {"state": state, "companies": count}
            for state, count in sorted(
                places.items(), key=lambda item: -item[1]
            )[:8]
        ],
    )


class DomainTally(BaseModel):
    """
    What one domain is worth looking at, for a page listing all of them.

    Deliberately not judged / rejected / couldn't-tell. Those describe how the
    filter performed, which is a question about the software; someone deciding
    where to spend an hour wants to know how many companies are worth reading
    and what a raise looks like there.
    """

    domain: str
    judged: int = 0
    fitted: int = 0
    rejected: int = 0
    unknown: int = 0
    latest_filing: str | None = None

    # What a raise looks like in this domain, over the companies it accepted.
    typical_raise: int | None = None
    lower_quartile: int | None = None
    upper_quartile: int | None = None

    @property
    def has_run(self) -> bool:
        return self.judged > 0


def domain_tallies(
    connection: sqlite3.Connection,
    configured: list[str] | tuple[str, ...] | None = None,
) -> list[DomainTally]:
    """
    Every domain and what it has turned up, busiest first.

    `configured` is the list of thesis files on disk. Passing it includes a
    domain that has never run — which is the state a newly added one is in, and
    exactly when someone wants to see it listed rather than wonder whether the
    file took effect.
    """
    rows = connection.execute(
        """
        SELECT theme,
               COUNT(*) AS judged,
               SUM(COALESCE(user_verdict, verdict) = 'fits')    AS fitted,
               SUM(COALESCE(user_verdict, verdict) = 'no_fit')  AS rejected,
               SUM(COALESCE(user_verdict, verdict) = 'unknown') AS unknown,
               MAX(filed_date) AS latest
        FROM candidate
        WHERE theme IS NOT NULL
        GROUP BY theme
        """
    ).fetchall()

    found = {
        row["theme"]: DomainTally(
            domain=row["theme"],
            judged=row["judged"],
            fitted=row["fitted"] or 0,
            rejected=row["rejected"] or 0,
            unknown=row["unknown"] or 0,
            latest_filing=row["latest"],
        )
        for row in rows
    }

    # Deal sizes over the companies each domain accepted, which is the set a
    # reader would actually be pricing against.
    for domain, tally in found.items():
        amounts = [
            row["offering_amount"]
            for row in connection.execute(
                "SELECT offering_amount FROM candidate WHERE theme = ? "
                "AND COALESCE(user_verdict, verdict) = 'fits' "
                "AND offering_amount IS NOT NULL AND offering_amount > 0",
                (domain,),
            )
        ]

        # Three is enough to say "roughly this much" about a shortlist someone
        # will read in full anyway. The market-wide benchmark needs eight; this
        # is a different claim about a smaller, hand-checkable set.
        if len(amounts) >= 3:
            amounts.sort()
            tally.typical_raise = int(statistics.median(amounts))
            tally.lower_quartile = amounts[0]
            tally.upper_quartile = amounts[-1]

    for domain in configured or ():
        found.setdefault(domain, DomainTally(domain=domain))

    return sorted(found.values(), key=lambda tally: (-tally.judged, tally.domain))


def subdomain_counts(
    connection: sqlite3.Connection,
    theme: str,
    fits_only: bool = True,
) -> list[dict]:
    """
    How one domain divides up, using its own criteria as the divisions.

    A global category list cannot do this. It has seven buckets for healthcare
    and one for energy, because healthcare was written first — so Energy's
    eighteen companies all land in "energy and climate" and the breakdown says
    nothing. The thesis's own "looking for" lines are the right divisions, and
    they change when someone edits the criteria, which is what you want.
    """
    clauses = ["theme = ?", "subdomain IS NOT NULL", "subdomain != ''"]
    parameters: list[object] = [theme]

    if fits_only:
        clauses.append("COALESCE(user_verdict, verdict) = 'fits'")

    rows = connection.execute(
        "SELECT subdomain, offering_amount FROM candidate "
        "WHERE " + " AND ".join(clauses),
        parameters,
    ).fetchall()

    grouped: dict[str, list[int]] = {}
    counts: dict[str, int] = {}

    for row in rows:
        counts[row["subdomain"]] = counts.get(row["subdomain"], 0) + 1

        if row["offering_amount"]:
            grouped.setdefault(row["subdomain"], []).append(row["offering_amount"])

    def typical(amounts: list[int]) -> int | None:
        # Two is enough here. This describes a handful of companies someone will
        # read in full, not a market — and saying nothing about a line with two
        # companies is less useful than saying "these two were about this big".
        return int(statistics.median(amounts)) if len(amounts) >= 2 else None

    return [
        {
            "subdomain": line,
            "companies": count,
            "raised": sum(grouped.get(line, [])),
            "typical": typical(grouped.get(line, [])),
        }
        for line, count in sorted(counts.items(), key=lambda item: -item[1])
    ]


def save_researchers(
    connection: sqlite3.Connection,
    accession: str,
    person_name: str,
    researcher,
    checked_at: str | None = None,
) -> None:
    """
    Store what was found for one person at one company, match or not.

    A miss is recorded too. Without it every run re-searches the same names
    against a service that asks politely to be left alone.
    """
    connection.execute(
        """
        INSERT INTO researcher (
            accession, person_name, openalex_id, display_name, works,
            citations, institution, topics, plausible, checked_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (accession, person_name) DO UPDATE SET
            openalex_id  = excluded.openalex_id,
            display_name = excluded.display_name,
            works        = excluded.works,
            citations    = excluded.citations,
            institution  = excluded.institution,
            topics       = excluded.topics,
            plausible    = excluded.plausible,
            checked_at   = excluded.checked_at
        """,
        (
            accession,
            person_name,
            getattr(researcher, "openalex_id", "") if researcher else "",
            getattr(researcher, "name", "") if researcher else "",
            getattr(researcher, "works", 0) if researcher else 0,
            getattr(researcher, "citations", 0) if researcher else 0,
            getattr(researcher, "institution", "") if researcher else "",
            json.dumps(getattr(researcher, "topics", []) if researcher else []),
            1 if (researcher and getattr(researcher, "plausible", False)) else 0,
            checked_at or datetime.now(UTC).isoformat(),
        ),
    )
    connection.commit()


def load_researchers(connection: sqlite3.Connection, accession: str) -> list:
    """Research records found for the people on one filing."""
    from src.research import Researcher

    rows = connection.execute(
        "SELECT * FROM researcher WHERE accession = ? AND display_name != '' "
        "ORDER BY works DESC",
        (accession,),
    ).fetchall()

    return [
        Researcher(
            name=row["display_name"],
            openalex_id=row["openalex_id"] or "",
            works=row["works"] or 0,
            citations=row["citations"] or 0,
            institution=row["institution"] or "",
            topics=json.loads(row["topics"] or "[]"),
            plausible=bool(row["plausible"]),
        )
        for row in rows
    ]
