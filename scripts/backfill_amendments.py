"""
Mark the archive's amendments as amendments.

Until the parser was fixed, every filing was read as new: the amendment flag
sits inside <newOrAmendment> and the parser looked one level up. The archive
kept the filings, but with is_amendment false on all of them. Signals need the
difference (a new round and an update to an old one are different news), so
this asks EDGAR which accessions were D/A and corrects those rows.

Free and idempotent: search pages only, no filing is downloaded again.

    .venv/bin/python scripts/backfill_amendments.py            # whole archive
    .venv/bin/python scripts/backfill_amendments.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.edgar import REQUEST_DELAY_SECONDS, SEARCH_URL, create_fetcher, parse_search_results, total_hits  # noqa: E402
from src.seen import connect  # noqa: E402


PAGE = 100


def amendment_accessions(fetch, start: str, end: str) -> set[str]:
    """Every D/A accession filed in a range, a week at a time so paging stays shallow."""
    found: set[str] = set()
    day = date.fromisoformat(start)
    last = date.fromisoformat(end)

    while day <= last:
        week_end = min(day + timedelta(days=6), last)
        offset = 0

        while True:
            params = {"forms": "D/A", "startdt": day.isoformat(), "enddt": week_end.isoformat()}
            if offset:
                params["from"] = offset

            raw = fetch(f"{SEARCH_URL}?{urlencode(params)}")
            payload = json.loads(raw) if isinstance(raw, str) else raw
            page = parse_search_results(payload)
            found.update(item["accession"] for item in page)

            offset += PAGE
            time.sleep(REQUEST_DELAY_SECONDS)

            if not page or offset >= total_hits(payload):
                break

        print(f"{day} to {week_end}: {len(found)} amendments so far", file=sys.stderr)
        day = week_end + timedelta(days=1)

    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with closing(connect()) as connection:
        start, end = connection.execute(
            "SELECT min(filed_date), max(filed_date) FROM archived_filing"
        ).fetchone()

        if not start:
            print("the archive is empty")
            return 0

        accessions = amendment_accessions(create_fetcher(), start, end)
        rows = [
            row for row in connection.execute(
                "SELECT accession, filing FROM archived_filing WHERE is_amendment = 0"
            )
            if row["accession"] in accessions
        ]

        print(f"{len(accessions)} amendments filed {start} to {end}; {len(rows)} in the archive need correcting")

        if args.dry_run:
            return 0

        for row in rows:
            filing = json.loads(row["filing"])
            filing["is_amendment"] = True
            connection.execute(
                "UPDATE archived_filing SET is_amendment = 1, filing = ? WHERE accession = ?",
                (json.dumps(filing), row["accession"]),
            )

        connection.commit()
        print(f"corrected {len(rows)} rows")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
