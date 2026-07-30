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

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_company (
    canonical_name   TEXT PRIMARY KEY,
    company_name     TEXT NOT NULL,
    canonical_domain TEXT,
    first_seen       TEXT NOT NULL,
    source           TEXT NOT NULL,
    accession        TEXT
);

-- Domains are the more reliable identity when we have one, but a Form D never
-- provides one, so it arrives later through enrichment and stays nullable.
CREATE INDEX IF NOT EXISTS idx_seen_domain
    ON seen_company (canonical_domain)
    WHERE canonical_domain IS NOT NULL;

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
    judged_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_candidate_verdict ON candidate (verdict);
CREATE INDEX IF NOT EXISTS idx_candidate_name ON candidate (canonical_name);
CREATE INDEX IF NOT EXISTS idx_candidate_filed ON candidate (filed_date DESC);
"""


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    """Open the index, creating the file and schema if needed."""
    location = db_path or DEFAULT_DB_PATH
    location.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(location)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)

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
