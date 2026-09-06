"""
Reading a typed sentence as filters.

The search box takes words. Most of what an analyst actually wants to ask is not
words but structure — a stage, a size, a domain, a verdict, a date — and those
are columns. This turns "pre-seed AI infra companies under $1M" into the query
that answers it, and hands whatever is left over to the text search.

No model. The vocabulary is small and known, so a parser is enough, and a parser
can be tested, costs nothing, and works when the API key does not. It also says
what it understood, because a search that silently reinterprets what you typed is
worse than one that ignores you.

What it cannot do is as important. "Technical founders" is not a column: the
filings name officers, and whether those people are technical was never looked
up. Rather than quietly dropping the phrase and returning a confident list that
does not honour it, the parser reports it as unsupported and says so on the page.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta

from pydantic import BaseModel, Field


# What a stage means as a cheque size. Round numbers, deliberately: these are
# conventions rather than measurements, and the interface shows the figure it
# used so nobody has to guess which convention was applied.
STAGE_CEILINGS = {
    "pre-seed": 3_000_000,
    "preseed": 3_000_000,
    "pre seed": 3_000_000,
    "seed": 15_000_000,
}

VERDICT_WORDS = {
    "fits": "fits",
    "fit": "fits",
    "maybe": "maybe",
    "maybes": "maybe",
    "unknown": "unknown",
    "unknowns": "unknown",
    "no fit": "no_fit",
    "no_fit": "no_fit",
    "not a fit": "no_fit",
    "rejected": "no_fit",
    "passed": "no_fit",
}

# Phrases a person will reasonably type that this radar cannot answer. Named so
# the page can say which part of the question went unanswered.
UNSUPPORTED = {
    "technical founders": "whether founders are technical is not recorded",
    "technical founder": "whether founders are technical is not recorded",
    "research founders": "founder backgrounds are not recorded",
    "repeat founders": "prior companies are not recorded",
    "revenue": "revenue is not in a Form D",
    "traction": "traction is not in a Form D",
    "valuation": "valuation is not in a Form D",
}

MULTIPLIERS = {"k": 1_000, "m": 1_000_000, "bn": 1_000_000_000, "b": 1_000_000_000}

AMOUNT = r"\$?\s*(\d+(?:\.\d+)?)\s*(k|m|bn|b)?"

BELOW = re.compile(r"(?:under|below|less than|<=?|up to)\s*" + AMOUNT, re.I)
ABOVE = re.compile(r"(?:over|above|more than|>=?|at least)\s*" + AMOUNT, re.I)


class ParsedQuery(BaseModel):
    """A typed sentence, read as filters plus leftover words."""

    text: str = ""
    verdicts: list[str] = Field(default_factory=list)
    theme: str | None = None
    min_amount: int | None = None
    max_amount: int | None = None
    since: str | None = None

    reading: list[str] = Field(default_factory=list)
    unsupported: list[str] = Field(default_factory=list)

    @property
    def is_structured(self) -> bool:
        """Whether anything beyond plain words was recognised."""
        return bool(self.reading)


def to_amount(number: str, suffix: str | None) -> int:
    return int(float(number) * MULTIPLIERS.get((suffix or "").lower(), 1))


def parse_query(text: str, themes: list[str] | None = None) -> ParsedQuery:
    """
    Read a sentence as filters.

    Recognised phrases are consumed; whatever survives becomes the text search,
    so "pre-seed cooling companies" filters by size and searches for "cooling".
    """
    remaining = f" {text.strip()} "
    parsed = ParsedQuery()

    def consume(pattern: str) -> bool:
        """Remove a matched phrase so it cannot also become a search word."""
        nonlocal remaining
        found = re.search(pattern, remaining, re.I)

        if found:
            remaining = remaining[: found.start()] + " " + remaining[found.end() :]

        return bool(found)

    # Things this cannot answer, first — so they are reported even when the rest
    # of the sentence parses cleanly and returns a plausible-looking list.
    for phrase, why in UNSUPPORTED.items():
        if consume(rf"\b{re.escape(phrase)}\b"):
            parsed.unsupported.append(why)

    below = BELOW.search(remaining)
    if below:
        parsed.max_amount = to_amount(below.group(1), below.group(2))
        parsed.reading.append(f"raising under {money(parsed.max_amount)}")
        consume(BELOW.pattern)

    above = ABOVE.search(remaining)
    if above:
        parsed.min_amount = to_amount(above.group(1), above.group(2))
        parsed.reading.append(f"raising over {money(parsed.min_amount)}")
        consume(ABOVE.pattern)

    # Stage only sets a ceiling if an explicit one was not already given, so
    # "seed under $2M" means two million rather than fifteen.
    for phrase, ceiling in STAGE_CEILINGS.items():
        if consume(rf"\b{re.escape(phrase)}\b"):
            if parsed.max_amount is None:
                parsed.max_amount = ceiling
                parsed.reading.append(f"{phrase} — under {money(ceiling)}")
            break

    for phrase, verdict in VERDICT_WORDS.items():
        if consume(rf"\b{re.escape(phrase)}\b") and verdict not in parsed.verdicts:
            parsed.verdicts.append(verdict)

    if parsed.verdicts:
        parsed.reading.append("judged " + " or ".join(parsed.verdicts))

    # Longest theme name first: "AI infra" must win over a shorter theme whose
    # name is a prefix of it.
    for name in sorted(themes or [], key=len, reverse=True):
        if consume(rf"\b{re.escape(name)}\b"):
            parsed.theme = name
            parsed.reading.append(f"in {name}")
            break

    since = parse_since(remaining, consume)
    if since:
        parsed.since, description = since
        parsed.reading.append(description)

    # Words that carry no meaning on their own would only narrow the text search
    # for no reason. "companies raising in energy" should search for nothing.
    filler = r"\b(?:companies|company|startups?|show|me|find|list|get|all|the|a|an|" \
             r"that|which|who|are|is|was|were|with|and|or|in|of|for|to|about|" \
             r"raising|raised|stage|round|rounds|any|please)\b"
    remaining = re.sub(filler, " ", remaining, flags=re.I)

    # Punctuation left behind by the phrases above would be searched for
    # literally: a trailing comma turns "cooling" into ", cooling", which matches
    # nothing. Keep only what can appear inside a company name.
    remaining = re.sub(r"[^\w\s&.'-]", " ", remaining)

    parsed.text = " ".join(word.strip(".-'") for word in remaining.split()).strip()

    # Only worth saying once something else was recognised. For a bare "cooling"
    # the reading would restate the box, which is noise; alongside "under $1M in
    # AI infra" it is the part a person cannot otherwise see was applied.
    if parsed.text and parsed.reading:
        parsed.reading.append(f"matching “{parsed.text}”")

    return parsed


def parse_since(text: str, consume) -> tuple[str, str] | None:
    """Read a date floor. Returns the ISO date and how to describe it."""
    today = datetime.now(UTC).date()

    if consume(r"\bthis year\b"):
        return date(today.year, 1, 1).isoformat(), f"filed in {today.year}"

    if consume(r"\b(?:this|last|past) month\b"):
        return (today - timedelta(days=30)).isoformat(), "filed in the last 30 days"

    if consume(r"\b(?:this|last|past) week\b"):
        return (today - timedelta(days=7)).isoformat(), "filed in the last 7 days"

    months = re.search(r"\b(?:last|past)\s+(\d+)\s+months?\b", text, re.I)
    if months:
        count = int(months.group(1))
        consume(r"\b(?:last|past)\s+\d+\s+months?\b")
        return (
            (today - timedelta(days=30 * count)).isoformat(),
            f"filed in the last {count} months",
        )

    year = re.search(r"\b(20\d{2})\b", text)
    if year:
        consume(r"\b20\d{2}\b")
        return f"{year.group(1)}-01-01", f"filed in {year.group(1)} or later"

    return None


def money(amount: int) -> str:
    if amount >= 1_000_000:
        return f"${amount / 1_000_000:.1f}M".replace(".0M", "M")

    return f"${amount // 1_000}k"
