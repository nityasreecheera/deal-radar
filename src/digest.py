"""
The digest: what actually reaches you.

Kept deliberately short. A digest that takes more than a couple of minutes to
read stops being read, and a radar nobody reads is worse than no radar, because
it feels like coverage.
"""

from __future__ import annotations

from pathlib import Path

from src.funding import describe_minimum, round_age, round_progress
from src.models import Candidate
from src.pipeline import RadarRun


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIGEST_DIR = PROJECT_ROOT / "outputs" / "digests"

VERDICT_MARK = {"fits": "✓", "maybe": "~", "unknown": "?", "no_fit": "✗"}


def format_amount(amount: int | None) -> str:
    """Render a raise the way an analyst reads it, not the way it is stored."""
    if amount is None:
        return "undisclosed"

    if amount >= 1_000_000:
        millions = amount / 1_000_000

        # 4.2M rather than 4.20M, and 18M rather than 18.0M.
        return f"${millions:.1f}M".replace(".0M", "M")

    return f"${amount / 1_000:.0f}k"


def format_location(candidate: Candidate) -> str:
    city = (candidate.filing.city or "").title()
    state = candidate.filing.state or ""

    if city and state:
        return f"{city}, {state}"

    return city or state or "location unknown"


def render_entry(
    index: int,
    candidate: Candidate,
    context: str = "",
) -> list[str]:
    """
    One company, as three or four short lines.

    `context` is how this company sits against the ones like it, worked out by
    the caller because it needs the database and this module deliberately does
    not touch one.
    """
    filing = candidate.filing
    mark = VERDICT_MARK[candidate.verdict]

    lines = [
        f"{index}. {filing.company_name} · "
        f"{format_amount(filing.total_offering_amount)} · "
        f"{format_location(candidate)}",
    ]

    # What they do comes before why it was judged that way. The first is what an
    # analyst is scanning for; the second is the argument.
    if candidate.summary:
        lines.append(f"   {candidate.summary}")

    lines.append(f"   {mark} {candidate.reason}")

    if filing.is_newly_incorporated:
        # A company raising in the year it was formed is the earliest stage
        # there is, and worth calling out explicitly.
        lines.append(f"   incorporated {filing.year_of_incorporation}")

    # How far through the raise they were. This is the line that changes what
    # you do about a company rather than merely describing it: a round that has
    # already sold out is not one you can join.
    percent, note = round_progress(
        filing.total_offering_amount, filing.total_amount_sold
    )

    if percent is not None:
        lines.append(f"   {percent}% sold — {note.replace(' when filed', '')}")

    # How old the deal actually is. Without this every company in the list looks
    # equally new, because the filing date is when the paperwork arrived rather
    # than when the round opened. Only said when it is not obvious — a round
    # filed the week it opened needs no comment.
    days, age = round_age(filing.first_sale_date, filing.filed_date)

    if days is not None and days > 14:
        lines.append(f"   first money in {filing.first_sale_date} — {age}")

    # Who the round is built for, in one number.
    minimum = describe_minimum(filing.minimum_investment)

    if minimum:
        lines.append(f"   {minimum}")

    # Where this sits among the ones like it. Last of the judgement lines,
    # because it is context for the decision rather than part of it.
    if context:
        lines.append(f"   {context}")

    if candidate.website:
        lines.append(f"   {candidate.website}")

    return lines


def render_digest(
    run: RadarRun,
    thesis_name: str,
    contexts: dict[str, str] | None = None,
    clusters: str = "",
) -> str:
    """
    Render a run as the message that gets sent.

    `contexts` maps accession to a line about how that company sits against the
    others in its category, and `clusters` is the standing pattern in what gets
    rejected. Both are passed in rather than looked up, so this module keeps
    rendering and nothing else.
    """
    interesting = run.interesting

    header = (
        f"Deal Radar · {len(interesting)} new · {thesis_name} · {run.end_date}"
    )

    lines = [header, ""]

    if not interesting:
        # "Nothing new matched" is a finding. It is only true if the radar
        # actually looked, and on a day EDGAR was down it hasn't. Saying it
        # anyway is the one lie this thing could tell that would matter.
        if run.unsearched:
            lines.append(
                "Nothing new matched what could be searched — but "
                f"{len(run.unsearched)} of "
                f"{len(run.unsearched) + run.searched_count} categories "
                "could not be reached, so this is not a clear day."
            )
        elif run.unexamined:
            # Fetched, filtered, and then nothing could be looked up or judged.
            # Reporting that as "nothing matched" claims a conclusion the run
            # never reached.
            lines.append(
                f"{run.unexamined} new companies were found but none could be "
                "examined — the lookup or the model failed on every one. "
                "This is not a quiet day; nothing was actually judged."
            )
        else:
            lines.append("Nothing new matched the thesis.")
    else:
        for index, candidate in enumerate(interesting, start=1):
            lines.extend(
                render_entry(
                    index,
                    candidate,
                    (contexts or {}).get(candidate.filing.accession, ""),
                )
            )
            lines.append("")

    # The skipped count is the point of the whole thing: it is the work that did
    # not land on anyone's desk.
    if run.skipped_count:
        lines.append(
            f"Skipped {run.skipped_count} filings — already seen or filtered out."
        )

    rejected = [c for c in run.candidates if c.verdict == "no_fit"]

    if rejected:
        lines.append(f"Judged {len(rejected)} as not a fit.")

    # Named, not listed. Knowing the count matters — it says how much the radar
    # could not find out — but the names belong on a research list rather than in
    # a two-minute read.
    if run.unknowns:
        lines.append(
            f"{len(run.unknowns)} could not be identified at all — "
            "see the unknown list."
        )

    # Last of the counting lines. Everything above is about this morning; this
    # is about the quarter, and interleaving the two makes both harder to read.
    if clusters:
        lines.append("")
        lines.append(clusters)

    # Above the problem list, because a coverage gap is not a footnote —
    # it changes what the rest of the email means.
    if run.unsearched:
        lines.append("")
        lines.append(
            f"⚠ Could not search: {', '.join(run.unsearched)}. "
            "EDGAR was unreachable for these, so anything filed under them "
            "has not been seen. Nothing was marked as seen either, so a "
            "successful run still covering this window will pick them up — "
            "but if this repeats for longer than the window, those days are "
            "a real gap. Re-run the dates by hand if it does."
        )

    if run.problems:
        lines.append("")
        lines.append(f"{len(run.problems)} problems:")
        lines.extend(f"  - {problem}" for problem in run.problems[:5])

    return "\n".join(lines).rstrip() + "\n"


def save_digest(
    content: str,
    run: RadarRun,
    output_directory: Path | None = None,
) -> Path:
    """
    Write the digest to disk so a past digest can be audited.

    Knowing what was sent, and therefore what was surfaced and when, matters as
    much as sending it.
    """
    directory = output_directory or DEFAULT_DIGEST_DIR
    directory.mkdir(parents=True, exist_ok=True)

    path = directory / f"{run.end_date}.md"
    temporary = path.with_suffix(".md.tmp")

    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)

    return path
