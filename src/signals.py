"""
What the filings let you say about a company, scored.

Deliberately not a success probability. A probability needs outcomes to
calibrate against, and this project has none — no company on record has been
acquired, failed, or floated. A number claiming "73% likely to succeed" would be
invented, and would look exactly as confident as a real one.

What this measures is evidence: how many of the things worth knowing are
present, out of the things we can actually check. A company scoring 8 is not more
likely to succeed than one scoring 3. It is one we know more good things about,
which is a smaller claim and a true one.

Every point is traceable to a field on a filing, and the interface shows which
signals fired and which did not — because a score nobody can take apart is an
opinion wearing a number's clothes.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, computed_field


class Signal(BaseModel):
    """One checkable thing, and what its presence suggests."""

    name: str
    weight: int = Field(ge=1)
    fired: bool = False

    # What the reader learns from it. Shown next to the signal, because a
    # checklist of jargon is not evidence anyone can weigh.
    means: str = ""

    # The number behind it, when there is one. "82% sold" beats a tick.
    detail: str = ""


class Assessment(BaseModel):
    """Everything the filings support, added up."""

    points: int = 0
    possible: int = 0
    signals: list[Signal] = Field(default_factory=list)

    @property
    def fired(self) -> list[Signal]:
        return [s for s in self.signals if s.fired]

    @property
    def missing(self) -> list[Signal]:
        return [s for s in self.signals if not s.fired]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def out_of_ten(self) -> int:
        """
        Rounded to ten, because a score of 7/23 invites false precision.

        A computed_field, not a plain property: a property is not serialised,
        so it never reaches the browser. That has now cost time three times in
        this project — is_unread, filing_url, and this.
        """
        if not self.possible:
            return 0

        return round(10 * self.points / self.possible)

    def describe(self) -> str:
        """One line, honest about what the number is."""
        if not self.possible:
            return "Nothing checkable on this filing."

        return (
            f"{self.out_of_ten} of 10 on evidence — "
            f"{len(self.fired)} of {len(self.signals)} signals present."
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

    # --- what we could find out ---------------------------------------------
    signals.append(
        Signal(
            name="Findable online",
            weight=1,
            fired=bool(candidate.website),
            means="there is something to check; silence is not evidence",
            detail=candidate.website or "no website found",
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

    return Assessment(
        points=sum(s.weight for s in signals if s.fired),
        possible=sum(s.weight for s in signals),
        signals=signals,
    )
