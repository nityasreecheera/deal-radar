"""
The archive: every Form D EDGAR publishes, kept whether or not anyone judges it.

The daily run only asks EDGAR about the industry groups some domain names, and
only for the last few days. That is right for an inbox and wrong for anything
that looks back. A domain added today could never see last month, and a group
nobody searched — "Other", "Business Services" — could never be measured to see
whether it was worth searching.

So this keeps all of it. Reading EDGAR is free and the rows are small; around
three hundred filings a weekday, two thirds of them investment funds. What costs
money is looking a company up and judging it, and the archive does neither.
Those happen only when a domain's run reads from here.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, timedelta

from pydantic import BaseModel, Field

from src.edgar import SearchOutcome, fetch_filings
from src.models import FormDFiling


# Pooled funds are most of what files a Form D. They are kept, because the
# archive is a record of what was filed, but flagged so nothing has to work out
# again that a private equity fund is not a startup.
FUND_GROUP = "Pooled Investment Fund"

# Results per day before the search stops. A busy weekday is around three
# hundred, so this only matters if EDGAR changes, and a cap that is reached is
# reported rather than passed off as a quiet day.
MAX_PER_DAY = 3000


class ArchivedDay(BaseModel):
    day: str
    filings: int = 0
    problems: list[str] = Field(default_factory=list)
    complete: bool = True


class ArchiveRun(BaseModel):
    """What one pass over EDGAR stored, a day at a time."""

    days: list[ArchivedDay] = Field(default_factory=list)

    @property
    def filings(self) -> int:
        return sum(day.filings for day in self.days)

    @property
    def incomplete(self) -> list[str]:
        return [day.day for day in self.days if not day.complete]


class Coverage(BaseModel):
    """Which days in a range the archive has read in full."""

    start_date: str
    end_date: str
    complete: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return not self.missing


def days_between(start_date: str, end_date: str) -> list[str]:
    """Every calendar day from start to end, inclusive."""
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)

    return [
        (start + timedelta(days=offset)).isoformat()
        for offset in range((end - start).days + 1)
    ]


def save_filing(connection: sqlite3.Connection, filing: FormDFiling) -> None:
    """Store one filing, replacing any earlier copy of the same accession."""
    connection.execute(
        """
        INSERT INTO archived_filing (
            accession, cik, company_name, filed_date, industry_group,
            is_fund, is_amendment, offering_amount, filing, archived_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (accession) DO UPDATE SET
            cik = excluded.cik,
            company_name = excluded.company_name,
            filed_date = excluded.filed_date,
            industry_group = excluded.industry_group,
            is_fund = excluded.is_fund,
            is_amendment = excluded.is_amendment,
            offering_amount = excluded.offering_amount,
            filing = excluded.filing,
            archived_at = excluded.archived_at
        """,
        (
            filing.accession,
            filing.cik,
            filing.company_name,
            filing.filed_date,
            filing.industry_group,
            int(filing.industry_group == FUND_GROUP),
            int(filing.is_amendment),
            filing.total_offering_amount,
            filing.model_dump_json(),
            datetime.now(UTC).isoformat(),
        ),
    )


def record_day(connection: sqlite3.Connection, day: ArchivedDay) -> None:
    """
    Note that a day was read, and whether it was read in full.

    A day read in full is never downgraded by a later partial read of it: what
    was stored the first time is still stored.
    """
    connection.execute(
        """
        INSERT INTO archived_day (day, filings, problems, complete, archived_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (day) DO UPDATE SET
            filings = MAX(archived_day.filings, excluded.filings),
            problems = excluded.problems,
            complete = MAX(archived_day.complete, excluded.complete),
            archived_at = excluded.archived_at
        """,
        (
            day.day,
            day.filings,
            len(day.problems),
            int(day.complete),
            datetime.now(UTC).isoformat(),
        ),
    )


def archive_range(
    connection: sqlite3.Connection,
    start_date: str,
    end_date: str,
    fetch_filings=fetch_filings,
    max_per_day: int = MAX_PER_DAY,
) -> ArchiveRun:
    """
    Read every Form D filed in a range from EDGAR and store it.

    One day at a time, so a failure loses that day rather than the range, and
    so each day can be recorded as read or not. A day counts as complete only
    if its search worked, nothing hit the cap, and every filing it listed could
    be parsed; anything less is stored as far as it got and marked incomplete,
    so a later pass fills it in.
    """
    run = ArchiveRun()

    for day in days_between(start_date, end_date):
        outcome = fetch_filings(day, day, industry_groups=None, max_per_group=max_per_day)

        for filing in outcome.filings:
            save_filing(connection, filing)

        result = ArchivedDay(
            day=day,
            filings=len(outcome.filings),
            problems=list(outcome.problems),
            complete=outcome.is_complete and not outcome.problems,
        )
        record_day(connection, result)
        connection.commit()

        run.days.append(result)

    return run


def coverage(connection: sqlite3.Connection, start_date: str, end_date: str) -> Coverage:
    """Which days in the range the archive has read in full, and which it has not."""
    complete = {
        row["day"]
        for row in connection.execute(
            "SELECT day FROM archived_day WHERE complete = 1 AND day BETWEEN ? AND ?",
            (start_date, end_date),
        )
    }
    days = days_between(start_date, end_date)

    return Coverage(
        start_date=start_date,
        end_date=end_date,
        complete=[day for day in days if day in complete],
        missing=[day for day in days if day not in complete],
    )


def archived_filings(
    connection: sqlite3.Connection,
    start_date: str,
    end_date: str,
    industry_groups: list[str] | tuple[str, ...],
) -> list[FormDFiling]:
    """Stored filings in the range whose stated group is one of these, newest first."""
    if not industry_groups:
        return []

    marks = ", ".join("?" for _ in industry_groups)
    rows = connection.execute(
        f"""
        SELECT filing FROM archived_filing
        WHERE filed_date BETWEEN ? AND ? AND industry_group IN ({marks})
        ORDER BY filed_date DESC, accession
        """,
        (start_date, end_date, *industry_groups),
    ).fetchall()

    return [FormDFiling.model_validate_json(row["filing"]) for row in rows]


def outcome_from_archive(
    connection: sqlite3.Connection,
    start_date: str,
    end_date: str,
    industry_groups: list[str] | tuple[str, ...],
) -> SearchOutcome:
    """
    The archive, shaped like a fetch from EDGAR, so the pipeline runs unchanged.

    Days the archive has not read in full are reported as problems. The
    pipeline would otherwise present a range with a hole in it as a range that
    was searched and found little.
    """
    filings = archived_filings(connection, start_date, end_date, industry_groups)
    gaps = coverage(connection, start_date, end_date).missing

    problems = []

    if gaps:
        shown = ", ".join(gaps[:5]) + (f" and {len(gaps) - 5} more" if len(gaps) > 5 else "")
        problems.append(
            f"the archive has not read {len(gaps)} day(s) in this range in full: {shown}"
        )

    return SearchOutcome(filings, problems, [], list(industry_groups))
