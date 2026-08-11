"""
The seen-index: the record of every company already surfaced.

This is the product. A radar's value is that it shows you only what you have
never seen, so this lookup has to be exact and provable — which is why it is
SQLite and not a memory system that recalls approximately.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from src.models import SeenCompany
from src.normalize import normalize_company_name, normalize_domain


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "radar.sqlite"

# Tables and indexes are declared separately because order matters. An index on
# a column that migration is about to add cannot be created before the column
# exists, so the sequence is: tables, then missing columns, then indexes. Doing
# it in one script fails on any database created before a column was added.
SCHEMA_TABLES = """
CREATE TABLE IF NOT EXISTS seen_company (
    canonical_name   TEXT PRIMARY KEY,
    company_name     TEXT NOT NULL,
    canonical_domain TEXT,
    first_seen       TEXT NOT NULL,
    source           TEXT NOT NULL,
    accession        TEXT
);

-- What we concluded, not merely that we looked.
--
-- The seen-index answers "have I encountered this company?" and that is all it
-- needs to do. This table answers "what did I decide, and why?" — which is the
-- question an analyst actually asks six months later, and the one that was
-- previously lost the moment a digest was rendered.
--
-- Keyed on accession rather than company, because a company can file more than
-- once and each filing is a separate judgement made on separate evidence.
CREATE TABLE IF NOT EXISTS candidate (
    accession        TEXT PRIMARY KEY,
    canonical_name   TEXT NOT NULL,
    company_name     TEXT NOT NULL,
    verdict          TEXT NOT NULL,
    reason           TEXT NOT NULL,
    website          TEXT,
    description      TEXT,
    offering_amount  INTEGER,
    filed_date       TEXT NOT NULL,
    industry_group   TEXT,
    city             TEXT,
    state            TEXT,
    incorporated     INTEGER,
    judged_at        TEXT NOT NULL,

    -- Which thesis reached this verdict. The same company can fit one theme and
    -- not another, so a verdict is meaningless without knowing what it was
    -- judged against.
    theme            TEXT,

    -- When a human actually read it. Null means unread, which is what the
    -- interface greys out or highlights.
    viewed_at        TEXT,

    -- Detail parsed from the filing and previously discarded on save. The
    -- officers and directors are the most useful part: a director based far
    -- from the company is often the investor's board seat.
    people           TEXT,   -- JSON array
    amount_sold      INTEGER,
    investor_count   INTEGER,
    jurisdiction     TEXT,
    entity_type      TEXT,
    cik              TEXT,   -- lets the interface link to the filing itself

    -- One line on what the company does. Distinct from `reason`, which explains
    -- the verdict; a detail view needs the business, not the decision.
    summary          TEXT
);

-- People named on filings, one row each.
--
-- These are stored as a JSON blob on the candidate too, which is fine for
-- displaying one company. This table exists for the opposite question: given a
-- person, which other companies are they on? That needs a join, and a join needs
-- rows.
CREATE TABLE IF NOT EXISTS person (
    accession     TEXT NOT NULL,
    name_key      TEXT NOT NULL,   -- lowercased, punctuation stripped
    full_name     TEXT NOT NULL,
    relationships TEXT,            -- comma separated, as filed
    city          TEXT,
    state         TEXT,
    PRIMARY KEY (accession, name_key)
);

-- Every Form D a company has ever filed, not only the ones this radar caught.
--
-- EDGAR knows a company's whole filing history, so a company that raised in 2023
-- and again now can be told apart from one raising for the first time. Those look
-- identical in a single filing and are completely different companies.
CREATE TABLE IF NOT EXISTS funding_round (
    accession       TEXT PRIMARY KEY,
    cik             TEXT NOT NULL,
    filed_date      TEXT NOT NULL,
    offering_amount INTEGER,
    amount_sold     INTEGER,
    is_amendment    INTEGER NOT NULL DEFAULT 0,
    fetched_at      TEXT NOT NULL
);
"""

SCHEMA_INDEXES = """
-- Domains are the more reliable identity when we have one, but a Form D never
-- provides one, so it arrives later through enrichment and stays nullable.
CREATE INDEX IF NOT EXISTS idx_seen_domain
    ON seen_company (canonical_domain)
    WHERE canonical_domain IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_candidate_verdict ON candidate (verdict);
CREATE INDEX IF NOT EXISTS idx_candidate_name ON candidate (canonical_name);
CREATE INDEX IF NOT EXISTS idx_candidate_filed ON candidate (filed_date DESC);
CREATE INDEX IF NOT EXISTS idx_candidate_theme ON candidate (theme);
CREATE INDEX IF NOT EXISTS idx_candidate_viewed ON candidate (viewed_at);

CREATE INDEX IF NOT EXISTS idx_person_name ON person (name_key);
CREATE INDEX IF NOT EXISTS idx_funding_cik ON funding_round (cik, filed_date);
"""


# Columns added after the table was already in use somewhere. CREATE TABLE IF
# NOT EXISTS does nothing to an existing table, so new columns have to be added
# explicitly or a deployed database silently lacks them.
MIGRATIONS: tuple[tuple[str, str, str], ...] = (
    # (table, column, DDL to add it)
    ("candidate", "theme", "ALTER TABLE candidate ADD COLUMN theme TEXT"),
    ("candidate", "viewed_at", "ALTER TABLE candidate ADD COLUMN viewed_at TEXT"),
    ("candidate", "people", "ALTER TABLE candidate ADD COLUMN people TEXT"),
    (
        "candidate",
        "amount_sold",
        "ALTER TABLE candidate ADD COLUMN amount_sold INTEGER",
    ),
    (
        "candidate",
        "investor_count",
        "ALTER TABLE candidate ADD COLUMN investor_count INTEGER",
    ),
    (
        "candidate",
        "jurisdiction",
        "ALTER TABLE candidate ADD COLUMN jurisdiction TEXT",
    ),
    (
        "candidate",
        "entity_type",
        "ALTER TABLE candidate ADD COLUMN entity_type TEXT",
    ),
    ("candidate", "cik", "ALTER TABLE candidate ADD COLUMN cik TEXT"),
    ("candidate", "summary", "ALTER TABLE candidate ADD COLUMN summary TEXT"),
    # The analyst's own call, kept alongside the model's rather than replacing
    # it. rejudge.py re-runs the model over stored rows, and a human decision
    # living in `verdict` would be silently overwritten the next time the prompt
    # changed. Keeping both also makes disagreement measurable, which is the
    # only real evidence of whether the thesis is any good.
    (
        "candidate",
        "user_verdict",
        "ALTER TABLE candidate ADD COLUMN user_verdict TEXT",
    ),
    ("candidate", "user_note", "ALTER TABLE candidate ADD COLUMN user_note TEXT"),
    ("candidate", "decided_at", "ALTER TABLE candidate ADD COLUMN decided_at TEXT"),
    (
        "candidate",
        "minimum_investment",
        "ALTER TABLE candidate ADD COLUMN minimum_investment INTEGER",
    ),
    (
        "candidate",
        "first_sale_date",
        "ALTER TABLE candidate ADD COLUMN first_sale_date TEXT",
    ),
)


def existing_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    """Column names on a table, or an empty set if the table is absent."""
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()

    return {row["name"] for row in rows}


def apply_migrations(connection: sqlite3.Connection) -> list[str]:
    """
    Add any columns missing from an existing database.

    Returns what was applied, so a caller can log it. Idempotent: running twice
    is a no-op, which matters because this runs on every connect.
    """
    applied: list[str] = []

    for table, column, statement in MIGRATIONS:
        columns = existing_columns(connection, table)

        if not columns or column in columns:
            continue

        connection.execute(statement)
        applied.append(f"{table}.{column}")

    if applied:
        connection.commit()

    return applied


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    """Open the index, creating or updating the schema as needed."""
    location = db_path or DEFAULT_DB_PATH
    location.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(location)
    connection.row_factory = sqlite3.Row

    # Order is deliberate: an index cannot be built on a column that migration
    # has not added yet.
    connection.executescript(SCHEMA_TABLES)
    apply_migrations(connection)
    connection.executescript(SCHEMA_INDEXES)

    return connection


def is_seen(
    connection: sqlite3.Connection,
    company_name: str,
    website: str | None = None,
) -> bool:
    """
    Whether this company has been surfaced before.

    Domain is checked first because it is the stronger identity: two filings can
    spell a name differently, but a domain is a domain.
    """
    domain = normalize_domain(website)

    if domain:
        row = connection.execute(
            "SELECT 1 FROM seen_company WHERE canonical_domain = ? LIMIT 1",
            (domain,),
        ).fetchone()

        if row is not None:
            return True

    canonical = normalize_company_name(company_name)

    if not canonical:
        return False

    row = connection.execute(
        "SELECT 1 FROM seen_company WHERE canonical_name = ? LIMIT 1",
        (canonical,),
    ).fetchone()

    return row is not None


def mark_seen(
    connection: sqlite3.Connection,
    company_name: str,
    source: str,
    website: str | None = None,
    accession: str | None = None,
    first_seen: str | None = None,
) -> SeenCompany:
    """
    Record a company as seen.

    Re-recording an existing company keeps the original first_seen date and only
    fills in a domain if one was previously missing. The first sighting is the
    fact worth preserving.
    """
    canonical = normalize_company_name(company_name)

    if not canonical:
        raise ValueError(f"cannot derive an identity from {company_name!r}")

    domain = normalize_domain(website)
    timestamp = first_seen or datetime.now(UTC).isoformat()

    connection.execute(
        """
        INSERT INTO seen_company
            (canonical_name, company_name, canonical_domain, first_seen,
             source, accession)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (canonical_name) DO UPDATE SET
            canonical_domain = COALESCE(
                seen_company.canonical_domain, excluded.canonical_domain
            )
        """,
        (canonical, company_name.strip(), domain, timestamp, source, accession),
    )
    connection.commit()

    row = connection.execute(
        "SELECT * FROM seen_company WHERE canonical_name = ?",
        (canonical,),
    ).fetchone()

    return SeenCompany(**dict(row))


def count_seen(connection: sqlite3.Connection) -> int:
    """How many companies the index holds."""
    row = connection.execute("SELECT COUNT(*) AS n FROM seen_company").fetchone()

    return int(row["n"])


def filter_unseen(
    connection: sqlite3.Connection,
    filings: list,
) -> tuple[list, int]:
    """
    Split filings into those never seen before and a count of those skipped.

    Deduplicates within the batch too: the same company can file twice in one
    window, and showing it twice in one digest would be as wrong as showing it
    across two days.
    """
    fresh: list = []
    skipped = 0
    batch_names: set[str] = set()

    for filing in filings:
        canonical = filing.canonical_name

        if not canonical or canonical in batch_names:
            skipped += 1
            continue

        if is_seen(connection, filing.company_name):
            skipped += 1
            continue

        batch_names.add(canonical)
        fresh.append(filing)

    return fresh, skipped


if __name__ == "__main__":
    with closing(connect()) as db:
        print(f"{count_seen(db)} companies in the index")
