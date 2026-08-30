"""
Look up the published work of people named on filings.

OpenAlex is free and needs no key, so this costs nothing but politeness. The
model is asked one thing per candidate — whether the research field plausibly
belongs to somebody founding this company — because that is a judgement and the
rest is mechanics.

    .venv/bin/python scripts/find_researchers.py [limit]

Safe to re-run. A person already checked is skipped, including one where nothing
was found: recording the miss is what stops the next run searching the same name
again.
"""

from __future__ import annotations

import json
import sys
import time
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.candidates import save_researchers  # noqa: E402
from src.judge import create_openai_compatible_judge  # noqa: E402
from src.research import (  # noqa: E402
    Unavailable,
    candidates_for,
    check_plausible,
    create_lookup,
)
from src.seen import connect  # noqa: E402


DELAY_SECONDS = 0.4


def main() -> int:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 60

    lookup = create_lookup()
    judge = create_openai_compatible_judge()
    checked = matched = 0

    with closing(connect()) as connection:
        rows = connection.execute(
            """
            SELECT p.accession, p.full_name, c.company_name, c.summary, c.reason
            FROM person p
            JOIN candidate c ON c.accession = p.accession
            WHERE COALESCE(c.user_verdict, c.verdict) IN ('fits', 'maybe')
              AND NOT EXISTS (
                  SELECT 1 FROM researcher r
                  WHERE r.accession = p.accession AND r.person_name = p.full_name
              )
            ORDER BY c.filed_date DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        print(f"{len(rows)} people to look up")

        for row in rows:
            time.sleep(DELAY_SECONDS)
            checked += 1

            found = candidates_for(row["full_name"], lookup=lookup)

            if not found:
                # Recorded, so the next run does not search this name again.
                save_researchers(connection, row["accession"], row["full_name"], None)
                continue

            does = row["summary"] or row["reason"] or ""
            best = None

            try:
                for candidate in found:
                    if check_plausible(
                        candidate, row["company_name"], does, judge=judge
                    ):
                        candidate.plausible = True
                        best = candidate
                        break
            except Unavailable as exc:
                # Stop rather than record every remaining person as unmatched.
                # A run that could not ask must not look like one that asked
                # and got no for an answer.
                print(f"\n  stopped: the model is unavailable ({exc})")
                print(f"  checked {checked - 1}, nothing recorded for this one")

                return 1

            save_researchers(
                connection, row["accession"], row["full_name"], best or found[0]
            )

            if best:
                matched += 1
                print(
                    f"  {row['company_name'][:24]:26} {row['full_name'][:22]:24} "
                    f"{best.summary[:46]}"
                )

    print(f"\nchecked {checked}, plausible matches {matched}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
