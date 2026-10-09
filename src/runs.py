"""
Runs asked for from the website, against the archive, instead of waiting.

The schedule looks three days back once a weekday. That leaves two gaps: a new
or corrected domain has to wait until morning, and then can only see three
days. A run from here reads the archive instead of EDGAR, so it can cover any
range the archive holds, and it goes through the same pipeline as the morning
run — same filters, same "already seen" rule, same judgement.

What it adds is a limit on spending. Every company judged is a model call and
possibly a web search, paid for by whoever owns the radar and triggered by a
button. So a run is capped, only one runs at a time, and the page shows what a
run would cost before it is started.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import closing
from datetime import UTC, date, datetime, timedelta

from pydantic import BaseModel, Field, model_validator

from src.archive import archived_filings, coverage, outcome_from_archive
from src.enrich import enrich_filing
from src.judge import judge_filing
from src.pipeline import recall_enrichment, run_radar
from src.seen import connect, filter_unseen
from src.thesis import Thesis, apply_filters


# Most companies one click may judge. Each is a model call and up to one web
# search, so this is a spending limit before it is anything else.
MAX_CAP = int(os.getenv("RUN_NOW_MAX", "100"))

# Longest range one run may cover. The cap already bounds the cost; this bounds
# how much of the archive a single preview has to read.
MAX_SPAN_DAYS = 366

# A run still marked as running after this long did not finish — the process
# was restarted under it — and must not block every run after it.
STALE_AFTER = timedelta(hours=3)

# Two clicks arriving together must not both pass the "nothing is running"
# check. The API is one process, so a lock in it is enough.
_starting = threading.Lock()


class RunRequest(BaseModel):
    """A range to run one domain over, and how many companies at most."""

    start_date: str
    end_date: str
    cap: int = Field(default=MAX_CAP, ge=1)

    @model_validator(mode="after")
    def check(self) -> "RunRequest":
        try:
            start = date.fromisoformat(self.start_date)
            end = date.fromisoformat(self.end_date)
        except ValueError as exc:
            raise ValueError("dates must be YYYY-MM-DD") from exc

        if start > end:
            raise ValueError("the start date is after the end date")

        if end > datetime.now(UTC).date():
            raise ValueError("the end date is in the future")

        if (end - start).days + 1 > MAX_SPAN_DAYS:
            raise ValueError(f"a run can cover at most {MAX_SPAN_DAYS} days")

        if self.cap > MAX_CAP:
            raise ValueError(f"a run can judge at most {MAX_CAP} companies")

        return self


class ManualRun(BaseModel):
    id: int
    theme: str
    start_date: str
    end_date: str
    cap: int
    status: str
    requested_at: str
    finished_at: str | None = None
    judged: int = 0
    fits: int = 0
    maybe: int = 0
    unexamined: int = 0
    problems: list[str] = Field(default_factory=list)
    message: str | None = None


class RunPreview(BaseModel):
    """
    What a run would do, worked out without doing any of it.

    `lookups` is an upper bound. A company another domain already looked up is
    not looked up again, and those are subtracted; anything else might be.
    """

    theme: str
    start_date: str
    end_date: str
    cap: int
    archived: int = Field(ge=0)
    passed_filters: int = Field(ge=0)
    already_checked: int = Field(ge=0)
    to_check: int = Field(ge=0)
    left_over: int = Field(ge=0)
    model_calls: int = Field(ge=0)
    lookups: int = Field(ge=0)
    missing_days: list[str] = Field(default_factory=list)
    running: ManualRun | None = None


class RunInProgress(RuntimeError):
    """Raised when a run is asked for while another has not finished."""


def to_run(row: sqlite3.Row) -> ManualRun:
    data = dict(row)
    data["problems"] = json.loads(data["problems"] or "[]")

    return ManualRun(**data)


def get_run(connection: sqlite3.Connection, run_id: int) -> ManualRun | None:
    row = connection.execute("SELECT * FROM manual_run WHERE id = ?", (run_id,)).fetchone()

    return to_run(row) if row else None


def recent_runs(connection: sqlite3.Connection, limit: int = 10) -> list[ManualRun]:
    rows = connection.execute(
        "SELECT * FROM manual_run ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()

    return [to_run(row) for row in rows]


def close_stale(connection: sqlite3.Connection, now: datetime | None = None) -> int:
    """Mark runs that have been "running" implausibly long as failed."""
    cutoff = ((now or datetime.now(UTC)) - STALE_AFTER).isoformat()
    cursor = connection.execute(
        """
        UPDATE manual_run
        SET status = 'failed', finished_at = ?,
            message = 'Did not finish. The server was probably restarted while it ran.'
        WHERE status = 'running' AND requested_at < ?
        """,
        (datetime.now(UTC).isoformat(), cutoff),
    )
    connection.commit()

    return cursor.rowcount


def running_run(connection: sqlite3.Connection) -> ManualRun | None:
    close_stale(connection)
    row = connection.execute(
        "SELECT * FROM manual_run WHERE status = 'running' ORDER BY id DESC LIMIT 1"
    ).fetchone()

    return to_run(row) if row else None


def preview(
    connection: sqlite3.Connection,
    thesis: Thesis,
    request: RunRequest,
) -> RunPreview:
    """Count what a run would judge, and roughly what it would spend."""
    filings = archived_filings(
        connection, request.start_date, request.end_date, thesis.sec_industry_groups
    )
    kept, _ = apply_filters(filings, thesis)
    fresh, already = filter_unseen(connection, kept, theme=thesis.domain)
    chosen = fresh[: request.cap]

    return RunPreview(
        theme=thesis.domain,
        start_date=request.start_date,
        end_date=request.end_date,
        cap=request.cap,
        archived=len(filings),
        passed_filters=len(kept),
        already_checked=already,
        to_check=len(chosen),
        left_over=len(fresh) - len(chosen),
        model_calls=len(chosen),
        lookups=sum(1 for filing in chosen if recall_enrichment(connection, filing) is None),
        missing_days=coverage(connection, request.start_date, request.end_date).missing,
        running=running_run(connection),
    )


def start_run(
    connection: sqlite3.Connection,
    thesis: Thesis,
    request: RunRequest,
) -> ManualRun:
    """Record a run as started, or refuse if one is already going."""
    with _starting:
        current = running_run(connection)

        if current is not None:
            raise RunInProgress(
                f"a run for {current.theme} is still going; wait for it to finish"
            )

        cursor = connection.execute(
            """
            INSERT INTO manual_run (theme, start_date, end_date, cap, status, requested_at)
            VALUES (?, ?, ?, ?, 'running', ?)
            """,
            (
                thesis.domain,
                request.start_date,
                request.end_date,
                request.cap,
                datetime.now(UTC).isoformat(),
            ),
        )
        connection.commit()

    return get_run(connection, cursor.lastrowid)


def execute_run(
    run_id: int,
    thesis: Thesis,
    enrich=enrich_filing,
    judge=judge_filing,
) -> None:
    """
    Do the run and write down what happened.

    Opens its own connection, because it runs on a thread of its own after the
    request that started it has returned. Any failure ends the run as failed
    with the reason, rather than leaving it marked as running forever.
    """
    with closing(connect()) as connection:
        run = get_run(connection, run_id)

        if run is None:
            return

        try:
            result = run_radar(
                connection,
                thesis,
                run.start_date,
                run.end_date,
                fetch_filings=lambda start, end: outcome_from_archive(
                    connection, start, end, thesis.sec_industry_groups
                ),
                enrich=enrich,
                judge=judge,
                limit=run.cap,
            )
        except Exception as exc:  # noqa: BLE001 — whatever it was, the run is over
            connection.execute(
                """
                UPDATE manual_run SET status = 'failed', finished_at = ?, message = ?
                WHERE id = ?
                """,
                (datetime.now(UTC).isoformat(), f"The run failed: {exc}", run_id),
            )
            connection.commit()
            return

        verdicts = [candidate.verdict for candidate in result.candidates]

        connection.execute(
            """
            UPDATE manual_run
            SET status = 'done', finished_at = ?, judged = ?, fits = ?, maybe = ?,
                unexamined = ?, problems = ?, message = ?
            WHERE id = ?
            """,
            (
                datetime.now(UTC).isoformat(),
                len(verdicts),
                verdicts.count("fits"),
                verdicts.count("maybe"),
                result.unexamined,
                json.dumps(result.problems),
                describe(len(verdicts), result.unexamined),
                run_id,
            ),
        )
        connection.commit()


def describe(judged: int, unexamined: int) -> str:
    """One line on how it went, honest about a run that could not judge anything."""
    if judged == 0 and unexamined > 0:
        return (
            f"None of the {unexamined} companies could be examined — the lookup or "
            "the model failed on every one. Nothing was ruled in or out."
        )

    if judged == 0:
        return "Nothing new to judge in this range."

    if unexamined:
        return f"Judged {judged}. Another {unexamined} could not be examined and will be tried again."

    return f"Judged {judged}."
