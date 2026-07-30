"""
Show what the pipeline decided and why, one company per block.

For answering "why did nothing surface?" — a radar that rejects everything is
indistinguishable from a broken one unless you can see the reasoning.
"""

from __future__ import annotations

import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.edgar import fetch_filings  # noqa: E402
from src.enrich import enrich_filing  # noqa: E402
from src.judge import judge_filing  # noqa: E402
from src.seen import connect, filter_unseen  # noqa: E402
from src.thesis import apply_filters, load_thesis  # noqa: E402


def main() -> int:
    start = sys.argv[1] if len(sys.argv) > 1 else "2026-07-28"
    end = sys.argv[2] if len(sys.argv) > 2 else "2026-07-29"
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 6

    thesis = load_thesis()

    filings, problems = fetch_filings(
        start, end, industry_groups=thesis.sec_industry_groups, max_per_group=10
    )
    kept, dropped = apply_filters(filings, thesis)

    with closing(connect()) as db:
        fresh, already_seen = filter_unseen(db, kept)

    print(f"fetched {len(filings)} | kept {len(kept)} | fresh {len(fresh)}")
    print(f"dropped {len(dropped)} | already seen {already_seen}")

    for problem in problems:
        print(f"  problem: {problem}")

    print()

    for filing in fresh[:limit]:
        enrichment = enrich_filing(filing)

        print("=" * 72)
        print(f"{filing.company_name}  [{filing.industry_group}]")
        print(f"  location: {filing.city}, {filing.state}")
        print(f"  amount:   {filing.total_offering_amount}")
        print(f"  site:     {enrichment.website or 'NOT FOUND'}")
        print(f"  confident: {enrichment.confident}")

        description = (enrichment.description or "")[:220]
        print(f"  description: {description or 'NONE'}")

        try:
            candidate = judge_filing(filing, enrichment, thesis)
        except Exception as exc:  # noqa: BLE001
            print(f"  JUDGE FAILED: {exc}")
            continue

        print(f"  VERDICT: {candidate.verdict}")
        print(f"  REASON:  {candidate.reason}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
