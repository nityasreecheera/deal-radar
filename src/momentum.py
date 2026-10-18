"""
Positive signals: a company already judged files again, and something moved.

A verdict is a snapshot. The company keeps filing after it, and some of those
filings say more than the first one did: a bigger round, a round that filled, a
new director. This reads every later filing in the archive from a company some
domain has already judged, compares it with what that company filed before, and
writes down what changed in plain words.

Everything here comes from Form D and costs nothing. No search, no model.

Who sees a signal depends on the verdict. Fits, maybes, unknowns and companies
nobody has decided on get every signal. A company judged no fit, by the model or
by the owner, only comes back on a strong one, because a new raise does not
change what a company does, and a short list that fills with rejects stops being
read.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, date, datetime, timedelta

from pydantic import BaseModel


# A first filing and a second one within a month are usually one raise filed
# twice, or a correction. A new round is a later filing than that.
NEW_ROUND_GAP_DAYS = 30

# Below this a change is noise: a $100 "raise" filling up is not news.
MATERIAL_AMOUNT = 500_000

# How long an alert stays beside a verdict, and how far the highlights look back.
ALERT_DAYS = 30
HIGHLIGHT_DAYS = 7

# Which kind leads when a filing says several things at once.
PRIORITY = ("bigger_round", "round_filled", "sold_jump", "new_round", "investors_up", "new_people")

LEADERSHIP = ("Executive Officer", "Director")


class Fact(BaseModel):
    kind: str
    strong: bool
    text: str


class Signal(BaseModel):
    """One filing that said something new about a company already judged."""

    accession: str
    cik: str
    company_name: str
    filed_date: str
    kind: str
    strong: bool
    headline: str
    offering_amount: int | None = None
    amount_sold: int | None = None


class Highlight(BaseModel):
    """A signal as a reader sees it: the company, how it was judged, what changed."""

    accession: str
    candidate_accession: str
    company_name: str
    filed_date: str
    kind: str
    strong: bool
    headline: str
    offering_amount: int | None = None
    themes: list[str]
    verdict: str


def money(amount: int | None) -> str:
    if not amount:
        return "an undisclosed amount"
    if amount >= 1_000_000:
        return f"${amount / 1_000_000:.1f}M".replace(".0M", "M")
    return f"${amount / 1_000:.0f}K"


def facts_between(new: dict, earlier: list[dict]) -> list[Fact]:
    """
    What a filing says that the company's earlier filings did not.

    `new` and each of `earlier` are filings as plain dicts, in FormDFiling's
    field names. Only filings strictly before `new` should be passed.
    """
    if not earlier:
        return []

    facts: list[Fact] = []

    offering = new.get("total_offering_amount")
    sold = new.get("total_amount_sold")
    investors = new.get("investor_count")
    amendment = bool(new.get("is_amendment"))

    offers = [f["total_offering_amount"] for f in earlier if f.get("total_offering_amount")]
    solds = [f["total_amount_sold"] for f in earlier if f.get("total_amount_sold") is not None]
    counts = [f["investor_count"] for f in earlier if f.get("investor_count") is not None]
    previous_offer = max(offers) if offers else None
    previous_sold = max(solds) if solds else None
    previous_investors = max(counts) if counts else None

    latest = max(f["filed_date"] for f in earlier)
    gap = (date.fromisoformat(new["filed_date"]) - date.fromisoformat(latest)).days

    if not amendment and gap >= NEW_ROUND_GAP_DAYS:
        if (
            offering
            and previous_offer
            and offering >= 2 * previous_offer
            and offering >= MATERIAL_AMOUNT
        ):
            times = offering / previous_offer
            facts.append(Fact(
                kind="bigger_round",
                strong=True,
                text=f"new round of {money(offering)}, {times:.0f}x the last one",
            ))
        else:
            facts.append(Fact(
                kind="new_round",
                strong=False,
                text=f"new round of {money(offering)}",
            ))

    if (
        amendment
        and offering
        and sold is not None
        and sold >= offering >= MATERIAL_AMOUNT
        and (previous_sold is None or previous_sold < offering)
    ):
        facts.append(Fact(kind="round_filled", strong=True, text=f"round fully sold ({money(offering)})"))
    elif (
        amendment
        and sold is not None
        and previous_sold
        and sold >= 2 * previous_sold
        and sold - previous_sold >= MATERIAL_AMOUNT
    ):
        facts.append(Fact(
            kind="sold_jump",
            strong=True,
            text=f"amount sold up from {money(previous_sold)} to {money(sold)}",
        ))

    if (
        investors is not None
        and previous_investors is not None
        and investors >= previous_investors + 10
        and investors >= 2 * previous_investors
    ):
        facts.append(Fact(
            kind="investors_up",
            strong=False,
            text=f"investors up from {previous_investors} to {investors}",
        ))

    known = {person_key(p) for f in earlier for p in f.get("related_persons") or []}
    arrivals = [
        p for p in new.get("related_persons") or []
        if person_key(p) not in known
        and any(role in LEADERSHIP for role in p.get("relationships") or [])
    ]

    # Only when the earlier filings named anyone at all. Otherwise everyone on
    # the new filing looks new, which says nothing about the company.
    if arrivals and known:
        names = ", ".join(full_name(p) for p in arrivals[:2])
        facts.append(Fact(kind="new_people", strong=False, text=f"new on the filing: {names}"))

    return sorted(facts, key=lambda fact: PRIORITY.index(fact.kind))


def person_key(person: dict) -> str:
    return full_name(person).lower()


def full_name(person: dict) -> str:
    return " ".join(
        part for part in (person.get("first_name"), person.get("last_name")) if part
    ).strip()


def earlier_filings(connection: sqlite3.Connection, cik: str, before: str) -> list[dict]:
    """
    Everything the company filed before a date: the archive, plus the funding
    history fetched from EDGAR for companies that were judged before the archive
    began. The archive keeps whole filings; the funding history keeps amounts.
    """
    key = cik.lstrip("0")
    found: dict[str, dict] = {}

    for row in connection.execute(
        "SELECT accession, filing FROM archived_filing "
        "WHERE ltrim(cik, '0') = ? AND filed_date < ?",
        (key, before),
    ):
        found[row["accession"]] = json.loads(row["filing"])

    for row in connection.execute(
        "SELECT accession, filed_date, offering_amount, amount_sold, is_amendment "
        "FROM funding_round WHERE ltrim(cik, '0') = ? AND filed_date < ?",
        (key, before),
    ):
        found.setdefault(row["accession"], {
            "filed_date": row["filed_date"],
            "total_offering_amount": row["offering_amount"],
            "total_amount_sold": row["amount_sold"],
            "is_amendment": bool(row["is_amendment"]),
        })

    return list(found.values())


def detect(connection: sqlite3.Connection, since: str) -> list[Signal]:
    """
    Find and store signals in archived filings on or after `since`.

    Only companies some domain has judged are looked at, and never the filing a
    judgement was made from. Each filing is looked at once: a filing already
    recorded is skipped, so running this every day costs almost nothing.
    """
    rows = connection.execute(
        """
        SELECT a.accession, a.cik, a.company_name, a.filed_date, a.filing
        FROM archived_filing a
        WHERE a.filed_date >= ?
          AND a.is_fund = 0
          AND ltrim(a.cik, '0') IN (
              SELECT ltrim(cik, '0') FROM main.candidate WHERE cik IS NOT NULL
          )
          AND a.accession NOT IN (SELECT accession FROM main.candidate)
          AND a.accession NOT IN (SELECT accession FROM momentum_signal)
        ORDER BY a.filed_date
        """,
        (since,),
    ).fetchall()

    found: list[Signal] = []

    for row in rows:
        new = json.loads(row["filing"])
        facts = facts_between(new, earlier_filings(connection, row["cik"], row["filed_date"]))

        if not facts:
            continue

        signal = Signal(
            accession=row["accession"],
            cik=row["cik"],
            company_name=row["company_name"],
            filed_date=row["filed_date"],
            kind=facts[0].kind,
            strong=any(fact.strong for fact in facts),
            headline="; ".join(fact.text for fact in facts),
            offering_amount=new.get("total_offering_amount"),
            amount_sold=new.get("total_amount_sold"),
        )
        save(connection, signal)
        found.append(signal)

    connection.commit()

    return found


def save(connection: sqlite3.Connection, signal: Signal) -> None:
    connection.execute(
        """
        INSERT OR IGNORE INTO momentum_signal (
            accession, cik, company_name, filed_date, kind, strong, headline,
            offering_amount, amount_sold, detected_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            signal.accession, signal.cik, signal.company_name, signal.filed_date,
            signal.kind, int(signal.strong), signal.headline,
            signal.offering_amount, signal.amount_sold,
            datetime.now(UTC).isoformat(),
        ),
    )


def _since(days: int, today: date | None = None) -> str:
    return ((today or date.today()) - timedelta(days=days)).isoformat()


def _rows(
    connection: sqlite3.Connection,
    since: str,
    theme: str | None = None,
) -> list[sqlite3.Row]:
    """
    Signals joined to the judgements they concern, one row per domain.

    Read through `candidate` deliberately. For a visitor that name is a view
    without the private domains, so a signal about a company only a private
    domain judged never reaches them.
    """
    query = """
        SELECT s.*, c.accession AS candidate_accession, c.theme,
               coalesce(c.user_verdict, c.verdict) AS effective
        FROM momentum_signal s
        JOIN candidate c ON ltrim(c.cik, '0') = ltrim(s.cik, '0')
        WHERE s.filed_date >= ?
    """
    params: list = [since]

    if theme:
        query += " AND c.theme = ?"
        params.append(theme)

    return connection.execute(query, params).fetchall()


def eligible(effective_verdict: str, strong: bool) -> bool:
    """Rejected companies come back only on a strong signal."""
    return strong or effective_verdict != "no_fit"


def highlights(
    connection: sqlite3.Connection,
    days: int = HIGHLIGHT_DAYS,
    limit: int = 10,
    theme: str | None = None,
    today: date | None = None,
) -> list[Highlight]:
    """
    The week's best signals, strongest first, then by size, then newest.

    Rolling: anything filed more than `days` ago falls off on its own.
    """
    merged: dict[str, Highlight] = {}

    for row in _rows(connection, _since(days, today), theme):
        if not eligible(row["effective"], bool(row["strong"])):
            continue

        existing = merged.get(row["accession"])

        if existing is None:
            merged[row["accession"]] = Highlight(
                accession=row["accession"],
                candidate_accession=row["candidate_accession"],
                company_name=row["company_name"],
                filed_date=row["filed_date"],
                kind=row["kind"],
                strong=bool(row["strong"]),
                headline=row["headline"],
                offering_amount=row["offering_amount"],
                themes=[row["theme"]] if row["theme"] else [],
                verdict=row["effective"],
            )
        elif row["theme"] and row["theme"] not in existing.themes:
            existing.themes.append(row["theme"])

            # The best verdict any domain gave, so "fits in one" is not hidden
            # behind "no fit in another".
            if VERDICT_RANK.get(row["effective"], 9) < VERDICT_RANK.get(existing.verdict, 9):
                existing.verdict = row["effective"]

    # Newest first, then a stable sort puts strong ones and bigger rounds on top.
    ranked = sorted(merged.values(), key=lambda h: h.filed_date, reverse=True)
    ranked.sort(key=lambda h: (not h.strong, -(h.offering_amount or 0)))

    return ranked[:limit]


VERDICT_RANK = {"fits": 0, "maybe": 1, "unknown": 2, "no_fit": 3}


def alerts_for(
    connection: sqlite3.Connection,
    ciks: list[str],
    days: int = ALERT_DAYS,
    today: date | None = None,
) -> dict[str, str]:
    """
    The strongest recent signal for each company that has one, keyed by CIK
    without leading zeros. Strong signals only: the symbol beside a verdict
    should mean "look at this again", and that is too loud for a new director.
    """
    keys = sorted({cik.lstrip("0") for cik in ciks if cik})

    if not keys:
        return {}

    placeholders = ", ".join("?" for _ in keys)
    rows = connection.execute(
        f"""
        SELECT ltrim(s.cik, '0') AS key, s.headline, s.filed_date
        FROM momentum_signal s
        WHERE s.strong = 1 AND s.filed_date >= ?
          AND ltrim(s.cik, '0') IN ({placeholders})
          AND ltrim(s.cik, '0') IN (SELECT ltrim(cik, '0') FROM candidate WHERE cik IS NOT NULL)
        ORDER BY s.filed_date DESC
        """,
        [_since(days, today), *keys],
    ).fetchall()

    alerts: dict[str, str] = {}

    for row in rows:
        alerts.setdefault(row["key"], f"{row['headline']} (filed {row['filed_date']})")

    return alerts


def unsent(
    connection: sqlite3.Connection,
    theme: str,
    limit: int = 5,
    days: int = HIGHLIGHT_DAYS,
    today: date | None = None,
) -> list[Highlight]:
    """A domain's signals that have not been in one of its emails yet."""
    sent = {
        row["accession"]
        for row in connection.execute(
            "SELECT accession FROM momentum_sent WHERE theme = ?", (theme,)
        )
    }
    waiting = [
        h for h in highlights(connection, days=days, limit=1_000, theme=theme, today=today)
        if h.accession not in sent
    ]

    return waiting[:limit]


def mark_sent(connection: sqlite3.Connection, theme: str, accessions: list[str]) -> None:
    now = datetime.now(UTC).isoformat()
    connection.executemany(
        "INSERT OR IGNORE INTO momentum_sent (accession, theme, sent_at) VALUES (?, ?, ?)",
        [(accession, theme, now) for accession in accessions],
    )
    connection.commit()


def render_section(signals: list[Highlight]) -> str:
    """The lines an email gets, or nothing when nothing moved."""
    if not signals:
        return ""

    lines = [f"Signals ({len(signals)}) — companies already judged that filed again"]

    for signal in signals:
        mark = "▲ " if signal.strong else "• "
        lines.append(
            f"{mark}{signal.company_name} · was {signal.verdict.replace('_', ' ')} · "
            f"{signal.headline} · filed {signal.filed_date}"
        )

    return "\n".join(lines)
