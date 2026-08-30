"""
What the filings let you say about a company, scored.

Deliberately not a success probability. A probability needs outcomes to
calibrate against, and this project has none — no company on record has been
acquired, failed, or floated. A number claiming "73% likely to succeed" would be
invented, and would look exactly as confident as a real one.

What this produces is two lists: what the filings say is true of a company, and
what they say is not. There is no total, because a total needs weights, and any
weighting of "raised before" against "ten investors" is a judgement invented here
rather than read off a filing — invisible to the reader and unarguable.

The weights that remain only order the list, so the signals that carry the most
sit at the top. Every line is traceable to a field on a filing.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, computed_field


class Signal(BaseModel):
    """One checkable thing, and what its presence suggests."""

    name: str

    # Ordering only. How much this signal carries relative to the others, used
    # to sort the list — never summed, because a total would present an
    # invented weighting as a measurement.
    weight: int = Field(ge=1)

    fired: bool = False

    # What the reader learns from it. Shown next to the signal, because a
    # checklist of jargon is not evidence anyone can weigh.
    means: str = ""

    # The number behind it, when there is one. "82% sold" beats a tick.
    detail: str = ""


class Assessment(BaseModel):
    """What the filings say is true of a company, and what they say is not."""

    signals: list[Signal] = Field(default_factory=list)

    @property
    def fired(self) -> list[Signal]:
        return [s for s in self.signals if s.fired]

    @property
    def missing(self) -> list[Signal]:
        return [s for s in self.signals if not s.fired]

    def describe(self) -> str:
        """One line for a human."""
        if not self.signals:
            return "Nothing checkable on this filing."

        return (
            f"{len(self.fired)} of {len(self.signals)} things we look for "
            "are true."
        )


def days_between(later: str | None, earlier: str | None) -> int | None:
    """Whole days, or None when either date is missing or malformed."""
    if not later or not earlier:
        return None

    try:
        return (date.fromisoformat(later) - date.fromisoformat(earlier)).days
    except ValueError:
        return None


def assess(candidate, history=None, today: str | None = None) -> Assessment:
    """
    Score one company on what its filings show.

    `history` is its funding history when known. The cross-filing signals are
    the strongest ones available — a round bigger than the last is the closest
    thing to market validation a filing can carry — so a company without a
    history is scored out of a smaller total rather than penalised for it.
    """
    year = int((today or date.today().isoformat())[:4])
    signals: list[Signal] = []

    # --- demand within this round -------------------------------------------
    offering = candidate.offering_amount
    sold = candidate.amount_sold

    if offering and sold is not None:
        share = sold / offering
        signals.append(
            Signal(
                name="Round nearly or fully sold",
                weight=2,
                fired=share >= 0.8,
                means="people wanted in; the raise was not a struggle",
                detail=f"{round(100 * share)}% sold when filed",
            )
        )

    if candidate.investor_count is not None:
        signals.append(
            Signal(
                name="Ten or more investors",
                weight=1,
                fired=candidate.investor_count >= 10,
                means="a syndicate rather than one cheque",
                detail=(
                    f"{candidate.investor_count} investor"
                    + ("" if candidate.investor_count == 1 else "s")
                ),
            )
        )

    if candidate.minimum_investment:
        signals.append(
            Signal(
                name="Institutional minimum",
                weight=1,
                fired=candidate.minimum_investment >= 100_000,
                means="built for funds, not friends and family",
                detail=f"${candidate.minimum_investment:,} minimum",
            )
        )

    # --- how early you are ---------------------------------------------------
    age = days_between(candidate.filed_date, candidate.first_sale_date)

    if age is not None:
        signals.append(
            Signal(
                name="Round still fresh",
                weight=2,
                fired=age <= 30,
                means="opened recently, so there may be room left",
                detail=(
                    f"opened {age} days before filing"
                    if age
                    else "opened the day it filed"
                ),
            )
        )

    if candidate.incorporated:
        signals.append(
            Signal(
                name="Recently incorporated",
                weight=1,
                fired=candidate.incorporated >= year - 2,
                means="early enough that a first cheque still matters",
                detail=f"incorporated {candidate.incorporated}",
            )
        )

    # --- who is behind it ----------------------------------------------------
    #
    # Replaces a "findable online" check, which fired on three quarters of
    # everything and told nobody anything. For a company with no product yet,
    # the founders' published work is sometimes the only evidence there is.
    researchers = getattr(candidate, "researchers", None) or []
    confirmed = [r for r in researchers if getattr(r, "plausible", False)]

    if researchers:
        best = max(confirmed or researchers, key=lambda r: r.works)

        signals.append(
            Signal(
                name="Founder with a research record",
                weight=3,
                fired=bool(confirmed),
                means=(
                    "published work in the field they are building in, which is "
                    "hard to acquire and hard to fake"
                ),
                detail=(
                    f"{best.name}: {best.summary}"
                    if confirmed
                    else "no record in a related field"
                ),
            )
        )

    # --- across filings, the strongest signals available ---------------------
    if history is not None and history.rounds:
        real = [r for r in history.rounds if not r.is_amendment]

        signals.append(
            Signal(
                name="Has raised before",
                weight=1,
                fired=len(real) > 1,
                means="somebody funded them once already",
                detail=(
                    "first raise on record"
                    if len(real) == 1
                    else f"{len(real)} raises on record"
                ),
            )
        )

        if len(real) > 1:
            previous = real[-2].offering_amount

            # The amended figure, not the one first filed. Cornelis Networks
            # opened at $25m and amended to $245m against a previous round of
            # $45m — comparing the opening number said "raising less than last
            # time" about a round five times the size. Same mistake as reporting
            # Proxima Bio's $88.5m and ignoring the $91.5m it became.
            grew = history.amended_upward
            latest = grew[1] if grew else real[-1].offering_amount

            if previous and latest:
                signals.append(
                    Signal(
                        name="Raising more than last time",
                        weight=3,
                        fired=latest > previous,
                        means=(
                            "the closest thing to validation a filing carries — "
                            "the last round did not put people off"
                        ),
                        detail=(
                            f"${previous:,} then ${latest:,}"
                            + (" after amendment" if grew else "")
                        ),
                    )
                )

            gap = days_between(real[-1].filed_date, real[-2].filed_date)

            if gap is not None:
                signals.append(
                    Signal(
                        name="Back within eighteen months",
                        weight=2,
                        fired=gap <= 550,
                        means="raising again quickly, rather than running dry slowly",
                        detail=f"{round(gap / 30.44)} months since the last raise",
                    )
                )

        if history.amended_upward:
            first, last = history.amended_upward
            signals.append(
                Signal(
                    name="Round grew after filing",
                    weight=2,
                    fired=True,
                    means="oversubscribed; they took more than they asked for",
                    detail=f"${first:,} raised to ${last:,}",
                )
            )

    # Heaviest first, so what carries the most sits at the top of each list.
    return Assessment(
        signals=sorted(signals, key=lambda s: -s.weight),
    )
