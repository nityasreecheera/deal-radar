"""
Re-judge stored candidates under the current thesis and prompt.

Needed when the prompt or verdict set changes: existing rows carry verdicts
reached under the old rules. The twelve "maybe — no evidence" rows are the reason
this exists, since they should now be "unknown".

Re-enriches as well as re-judging, because a verdict reached on absent evidence
deserves another look at the evidence before being reclassified. That makes this
cost money — roughly one search and one model call per row.

Usage:
    python scripts/rejudge.py [verdict] [limit]
    python scripts/rejudge.py maybe 25
"""

from __future__ import annotations

import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.candidates import list_candidates, save_candidate  # noqa: E402
from src.enrich import Enrichment, enrich_filing  # noqa: E402
from src.judge import judge_filing  # noqa: E402
from src.models import FormDFiling, RelatedPerson  # noqa: E402
from src.seen import connect  # noqa: E402
from src.thesis import load_thesis  # noqa: E402


def rebuild_filing(stored) -> FormDFiling:
    """
    Reconstruct enough of the filing to re-judge from what was stored.

    Everything the prompt uses is on the row, so this needs no network. The
    industry group falls back to a placeholder because it is not required for
    judging and an empty string would fail validation.
    """
    return FormDFiling(
        accession=stored.accession,
        cik=stored.cik or "0",
        company_name=stored.company_name,
        filed_date=stored.filed_date,
        industry_group=stored.industry_group or "Unknown",
        entity_type=stored.entity_type,
        jurisdiction=stored.jurisdiction,
        year_of_incorporation=stored.incorporated,
        city=stored.city,
        state=stored.state,
        total_offering_amount=stored.offering_amount,
        total_amount_sold=stored.amount_sold,
        investor_count=stored.investor_count,
        related_persons=[
            RelatedPerson(**person.model_dump()) for person in stored.people
        ],
    )


def main() -> int:
    verdict = sys.argv[1] if len(sys.argv) > 1 else "maybe"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 25

    thesis = load_thesis()

    with closing(connect()) as connection:
        rows = list_candidates(connection, verdicts=[verdict], limit=limit)

        print(f"re-judging {len(rows)} rows currently '{verdict}'\n")

        changed = 0

        for stored in rows:
            filing = rebuild_filing(stored)

            try:
                enrichment = enrich_filing(filing)
            except Exception as exc:  # noqa: BLE001
                print(f"  {stored.company_name[:32]:32} enrichment failed ({exc})")
                enrichment = Enrichment()

            try:
                candidate = judge_filing(filing, enrichment, thesis)
            except Exception as exc:  # noqa: BLE001
                print(f"  {stored.company_name[:32]:32} judge failed ({exc})")
                continue

            moved = candidate.verdict != stored.verdict
            changed += 1 if moved else 0

            arrow = f"{stored.verdict} -> {candidate.verdict}" if moved else "unchanged"
            print(f"  {stored.company_name[:32]:32} {arrow}")

            save_candidate(connection, candidate, theme=stored.theme)

    print(f"\n{changed} of {len(rows)} moved")

    return 0


if __name__ == "__main__":
    sys.exit(main())
