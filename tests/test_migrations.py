"""
Schema migration, tested against a database built the old way.

CREATE TABLE IF NOT EXISTS does nothing to a table that already exists, so a
deployed database keeps whatever columns it was created with. The real database
on the deployment host already had rows before theme and viewed_at existed, and
without migration every query touching them would fail there while passing here.
"""

import sqlite3
from contextlib import closing
from pathlib import Path

from src.candidates import (
    count_unread,
    get_candidate,
    list_candidates,
    mark_viewed,
)
from src.seen import apply_migrations, connect, existing_columns


# The candidate table exactly as it was before theme and viewed_at were added.
OLD_SCHEMA = """
CREATE TABLE candidate (
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
"""


def build_old_database(path: Path) -> None:
    """Create a database in the pre-migration shape, with a row in it."""
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(OLD_SCHEMA)
        connection.execute(
            """
            INSERT INTO candidate (
                accession, canonical_name, company_name, verdict, reason,
                filed_date, judged_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "acc-old",
                "genomenon",
                "Genomenon, Inc.",
                "fits",
                "Judged before theme existed.",
                "2026-07-30",
                "2026-07-30T12:00:00+00:00",
            ),
        )
        connection.commit()


def test_the_old_shape_really_is_missing_the_columns(tmp_path: Path) -> None:
    path = tmp_path / "radar.sqlite"
    build_old_database(path)

    with closing(sqlite3.connect(path)) as connection:
        connection.row_factory = sqlite3.Row
        columns = existing_columns(connection, "candidate")

    assert "theme" not in columns
    assert "viewed_at" not in columns


def test_connecting_adds_the_missing_columns(tmp_path: Path) -> None:
    path = tmp_path / "radar.sqlite"
    build_old_database(path)

    with closing(connect(path)) as connection:
        columns = existing_columns(connection, "candidate")

        assert "theme" in columns
        assert "viewed_at" in columns


def test_existing_rows_survive_the_migration(tmp_path: Path) -> None:
    path = tmp_path / "radar.sqlite"
    build_old_database(path)

    with closing(connect(path)) as connection:
        stored = get_candidate(connection, "acc-old")

        assert stored is not None
        assert stored.company_name == "Genomenon, Inc."
        assert stored.reason == "Judged before theme existed."
        # Rows judged before themes existed have none, and that is not an error.
        # Filed under Healthcare rather than left null. The key is
        # (accession, theme) now and cannot hold a null half — and a judgement
        # made before themes existed WAS the healthcare thesis, because it was
        # the only one. Recording that is accurate, not a fudge.
        assert stored.theme == "Healthcare"
        assert stored.viewed_at is None
        assert stored.is_unread is True


def test_queries_on_the_new_columns_work_after_migrating(tmp_path: Path) -> None:
    path = tmp_path / "radar.sqlite"
    build_old_database(path)

    with closing(connect(path)) as connection:
        assert count_unread(connection) == 1
        assert len(list_candidates(connection, unread_only=True)) == 1

        mark_viewed(connection, "acc-old")

        assert count_unread(connection) == 0
        assert list_candidates(connection, unread_only=True) == []


def test_migrating_twice_changes_nothing(tmp_path: Path) -> None:
    path = tmp_path / "radar.sqlite"
    build_old_database(path)

    with closing(connect(path)) as connection:
        # connect() already migrated; a second pass must be a no-op.
        assert apply_migrations(connection) == []


def test_migration_reports_what_it_applied(tmp_path: Path) -> None:
    path = tmp_path / "radar.sqlite"
    build_old_database(path)

    with closing(sqlite3.connect(path)) as connection:
        connection.row_factory = sqlite3.Row
        applied = apply_migrations(connection)

    # The old shape lacks every column added since, so migration reports them
    # all. Asserting the exact list would mean editing this test on every future
    # addition; what matters is that it names what it did and covers these two.
    assert "candidate.theme" in applied
    assert "candidate.viewed_at" in applied
    # The re-key is reported too, and is not a column. Anything that is not a
    # column addition should be legible in the log rather than silent.
    assert all(
        entry.startswith("candidate.") or entry.startswith("candidate re-keyed")
        for entry in applied
    )


def test_a_fresh_database_needs_no_migration(tmp_path: Path) -> None:
    with closing(connect(tmp_path / "fresh.sqlite")) as connection:
        # The base schema already declares both columns.
        assert apply_migrations(connection) == []
        assert "theme" in existing_columns(connection, "candidate")


def test_two_domains_judging_one_filing_keep_both_verdicts(tmp_path) -> None:
    """
    The bug this exists for.

    The judgement table was keyed on the filing alone, so the second thesis to
    look at a company overwrote the first — verdict, reason, category and the
    domain label itself. 174 judgements were lost that way before anyone
    noticed, because nothing errored and each domain's own run looked fine.
    """
    from src.candidates import get_candidate, list_candidates, save_candidate
    from src.models import Candidate, FormDFiling

    def judgement(theme: str, verdict: str, reason: str) -> Candidate:
        return Candidate(
            filing=FormDFiling(
                accession="acc-shared",
                cik="1",
                company_name="Cornelis Networks, Inc.",
                filed_date="2026-08-01",
                industry_group="Other Technology",
            ),
            verdict=verdict,
            reason=reason,
        )

    with closing(connect(tmp_path / "radar.sqlite")) as db:
        save_candidate(db, judgement("AI tools", "no_fit", "Hardware."), theme="AI tools")
        save_candidate(db, judgement("AI infra", "fits", "Interconnect."), theme="AI infra")

        both = list_candidates(db)

        assert len(both) == 2
        assert {c.theme for c in both} == {"AI tools", "AI infra"}

        # Each domain's own verdict survives the other.
        assert get_candidate(db, "acc-shared", theme="AI tools").verdict == "no_fit"
        assert get_candidate(db, "acc-shared", theme="AI infra").verdict == "fits"


def test_rejudging_within_one_domain_still_replaces(tmp_path) -> None:
    from src.candidates import get_candidate, list_candidates, save_candidate
    from src.models import Candidate, FormDFiling

    def judgement(verdict: str) -> Candidate:
        return Candidate(
            filing=FormDFiling(
                accession="acc-1",
                cik="1",
                company_name="Acme",
                filed_date="2026-08-01",
                industry_group="Other Technology",
            ),
            verdict=verdict,
            reason="Because.",
        )

    with closing(connect(tmp_path / "radar.sqlite")) as db:
        save_candidate(db, judgement("maybe"), theme="Healthcare")
        save_candidate(db, judgement("fits"), theme="Healthcare")

        # Same filing, same domain: corrected, not duplicated.
        assert len(list_candidates(db)) == 1
        assert get_candidate(db, "acc-1").verdict == "fits"
