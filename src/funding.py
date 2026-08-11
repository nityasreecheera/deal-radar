"""
A company's whole funding history, not just the filing we happened to catch.

EDGAR knows every filing a company has ever made. That matters because a company
raising for the first time and a company raising for the third time look identical
in a single Form D, and they are completely different propositions.

Everything here is free. The submissions endpoint needs no key, and the filings
themselves are the same documents the radar already reads.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, date, datetime
from typing import Callable

from pydantic import BaseModel, Field

from src.edgar import EdgarError, create_fetcher, filing_xml_url, parse_form_d


SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"


class FundingRound(BaseModel):
    """One raise, as filed."""

    accession: str = Field(min_length=1)
    cik: str = Field(min_length=1)
    filed_date: str = Field(min_length=1)
    offering_amount: int | None = None
    amount_sold: int | None = None
    is_amendment: bool = False

    @property
    def year(self) -> str:
        return self.filed_date[:4]


class FundingHistory(BaseModel):
    """Every Form D a company has filed, oldest first."""

    cik: str = Field(min_length=1)
    rounds: list[FundingRound] = Field(default_factory=list)

    @property
    def first_raise(self) -> FundingRound | None:
        return self.rounds[0] if self.rounds else None

    @property
    def latest(self) -> FundingRound | None:
        return self.rounds[-1] if self.rounds else None

    @property
    def total_raised(self) -> int:
        """
        Everything actually sold across all rounds.

        Sold rather than offered, because an offering amount is a target and
        counting targets would overstate what a company has actually taken in.
        Amendments are skipped: they restate a round that is already counted.
        """
        return sum(
            r.amount_sold or 0 for r in self.rounds if not r.is_amendment
        )

    @property
    def is_first_time(self) -> bool:
        """Whether this company has never raised before."""
        return len([r for r in self.rounds if not r.is_amendment]) <= 1

    @property
    def amended_upward(self) -> tuple[int, int] | None:
        """
        Whether the most recent round grew after it was first filed.

        A company that opens at one number and amends to a higher one raised
        more than it set out to, which is worth saying. Proxima Bio opened at
        $88.5m and amended to $91.5m, and reporting only the original both
        understates the round and hides that it filled.

        Returns (original, amended) or None.
        """
        originals = [r for r in self.rounds if not r.is_amendment]
        amendments = [r for r in self.rounds if r.is_amendment]

        if not originals or not amendments:
            return None

        first = originals[-1].offering_amount
        last = amendments[-1].offering_amount

        if first is None or last is None or last <= first:
            return None

        return first, last

    def describe(self) -> str:
        """A plain sentence for a human, rather than a chart to interpret."""
        real = [r for r in self.rounds if not r.is_amendment]

        if not real:
            return "No filing history found."

        grew = self.amended_upward

        if len(real) == 1:
            opened = f"First raise on record, opened {real[0].filed_date}"

            if grew:
                return (
                    f"{opened} at ${grew[0]:,}, later amended up to ${grew[1]:,}."
                )

            return f"{opened}."

        span = f"{real[0].year} to {real[-1].year}"
        total = self.total_raised

        sentence = f"{len(real)} raises on record, {span}"
        sentence += f", ${total:,} sold in total." if total else "."

        if grew:
            sentence += f" The latest was amended up to ${grew[1]:,}."

        return sentence


def submissions_url(cik: str) -> str:
    """Where EDGAR keeps a company's filing index."""
    return SUBMISSIONS_URL.format(cik=int(str(cik).lstrip("0") or "0"))


def parse_form_d_accessions(payload: dict) -> list[tuple[str, str, bool]]:
    """
    Pull every Form D out of a submissions response.

    Returns (accession, filed_date, is_amendment), oldest first. "D/A" is an
    amendment to a round already filed, kept so the history is complete but
    flagged so it is not counted twice.
    """
    recent = (payload.get("filings") or {}).get("recent") or {}

    forms = recent.get("form") or []
    dates = recent.get("filingDate") or []
    numbers = recent.get("accessionNumber") or []

    found = [
        (accession, date, form == "D/A")
        for form, date, accession in zip(forms, dates, numbers)
        if form in ("D", "D/A")
    ]

    return sorted(found, key=lambda item: item[1])


def fetch_history(
    cik: str,
    fetch: Callable[[str], str] | None = None,
    max_rounds: int = 12,
) -> FundingHistory:
    """
    Fetch every Form D a company has filed, with amounts.

    One request for the index and one per filing. A filing that cannot be read is
    skipped rather than failing the history, because a partial history is still
    worth showing and a company with ten filings should not be lost to one bad
    document.
    """
    fetcher = fetch or create_fetcher()

    try:
        payload = json.loads(fetcher(submissions_url(cik)))
    except (EdgarError, json.JSONDecodeError) as exc:
        raise EdgarError(f"could not read filing history for {cik}: {exc}") from exc

    rounds: list[FundingRound] = []

    for accession, filed_date, is_amendment in parse_form_d_accessions(payload)[
        -max_rounds:
    ]:
        try:
            filing = parse_form_d(
                fetcher(filing_xml_url(cik, accession)),
                accession,
                filed_date,
            )
        except Exception:  # noqa: BLE001 - one unreadable filing is not fatal
            continue

        rounds.append(
            FundingRound(
                accession=accession,
                cik=str(cik),
                filed_date=filed_date,
                offering_amount=filing.total_offering_amount,
                amount_sold=filing.total_amount_sold,
                is_amendment=is_amendment,
            )
        )

    return FundingHistory(cik=str(cik), rounds=rounds)


def save_history(
    connection: sqlite3.Connection,
    history: FundingHistory,
    fetched_at: str | None = None,
) -> int:
    """Store a funding history. Returns how many rounds were written."""
    timestamp = fetched_at or datetime.now(UTC).isoformat()

    for round_ in history.rounds:
        connection.execute(
            """
            INSERT INTO funding_round (
                accession, cik, filed_date, offering_amount,
                amount_sold, is_amendment, fetched_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (accession) DO UPDATE SET
                offering_amount = excluded.offering_amount,
                amount_sold     = excluded.amount_sold,
                fetched_at      = excluded.fetched_at
            """,
            (
                round_.accession,
                round_.cik,
                round_.filed_date,
                round_.offering_amount,
                round_.amount_sold,
                1 if round_.is_amendment else 0,
                timestamp,
            ),
        )

    connection.commit()

    return len(history.rounds)


def load_history(
    connection: sqlite3.Connection,
    cik: str,
) -> FundingHistory:
    """Read a stored funding history, oldest first."""
    normalised = str(cik).lstrip("0") or "0"

    rows = connection.execute(
        """
        SELECT * FROM funding_round
        WHERE CAST(cik AS INTEGER) = CAST(? AS INTEGER)
        ORDER BY filed_date ASC
        """,
        (normalised,),
    ).fetchall()

    return FundingHistory(
        cik=str(cik),
        rounds=[
            FundingRound(
                accession=row["accession"],
                cik=row["cik"],
                filed_date=row["filed_date"],
                offering_amount=row["offering_amount"],
                amount_sold=row["amount_sold"],
                is_amendment=bool(row["is_amendment"]),
            )
            for row in rows
        ],
    )


def round_progress(
    offering_amount: int | None,
    amount_sold: int | None,
) -> tuple[int | None, str]:
    """
    How far through a raise a company was when it filed.

    Returns a percentage and a plain description. The percentage is None when
    there is nothing to divide, and the wording stays cautious on purpose: these
    numbers were true on the filing date, not today.
    """
    if not offering_amount:
        return None, "no target disclosed"

    if amount_sold is None:
        return None, "amount sold not disclosed"

    percent = round(100 * amount_sold / offering_amount)

    if percent >= 100:
        return percent, "fully sold when filed — likely closed"

    if percent >= 80:
        return percent, "nearly closed when filed"

    if percent >= 40:
        return percent, "part-raised when filed"

    if percent > 0:
        return percent, "just opened when filed"

    return 0, "nothing sold yet when filed"


def round_age(
    first_sale_date: str | None,
    filed_date: str,
) -> tuple[int | None, str]:
    """
    How long a round had been running by the time it was filed.

    This is the difference between the two dates a Form D carries, and it is the
    one that changes what you do. The filing date says when the paperwork
    arrived; the first-sale date says when money actually moved. Synthesis Health
    filed in August 2026 having taken its first money in July 2025 — a round that
    had been open a year, arriving in the inbox looking exactly as new as one
    opened last week.

    Returns days open and a phrase, or (None, ...) when there is nothing to
    compare.
    """
    if not first_sale_date:
        return None, "when it opened is not disclosed"

    try:
        opened = date.fromisoformat(first_sale_date)
        filed = date.fromisoformat(filed_date)
    except ValueError:
        return None, "when it opened is not disclosed"

    days = (filed - opened).days

    # A sale dated after the filing is a round that has not started. Reporting
    # that as negative days open would be nonsense.
    if days < 0:
        return None, "had not opened when filed"

    if days <= 14:
        return days, "just opened when filed"

    if days < 60:
        return days, f"open about {max(days // 7, 2)} weeks when filed"

    months = round(days / 30.44)

    if days < 365:
        return days, f"open about {months} months when filed"

    years = days / 365.25

    if years < 1.5:
        return days, "open over a year when filed"

    return days, f"open about {years:.0f} years when filed"


def describe_minimum(minimum: int | None) -> str | None:
    """
    Who the round is built for, from the smallest cheque it will take.

    Zero and None both mean "no floor stated", which is not the same as a floor
    of nothing — rendering it as "$0" would read as a number the company chose.
    """
    if not minimum:
        return None

    if minimum <= 1:
        # A $1 floor on a $91m round, as Proxima Bio filed, is not an open door.
        # It means the allocation is settled and they are accommodating whoever
        # is already in.
        return "no real minimum — allocation likely settled"

    if minimum < 25_000:
        return f"${minimum:,} minimum — friends and family sized"

    if minimum < 100_000:
        return f"${minimum:,} minimum — angel sized"

    return f"${minimum:,} minimum — institutional"
