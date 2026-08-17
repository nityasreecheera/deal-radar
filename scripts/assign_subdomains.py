"""
Say which criteria line each company matched.

Sub-domains are the thesis's own "looking for" lines, so this can only be
answered per domain, against the criteria as they stand. Reads the stored
summary and reason — no web search, no re-enrichment — and asks only the one
question, which is far cheaper than a full rejudge.

    .venv/bin/python scripts/assign_subdomains.py [limit]

Safe to re-run. Only rows without a subdomain are touched, and no verdict is
changed: this describes what a company is, not whether it fits.
"""

from __future__ import annotations

import json
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.judge import create_openai_compatible_judge, matched_line  # noqa: E402
from src.seen import connect  # noqa: E402
from src.thesis import load_all_theses  # noqa: E402


BATCH = 12

SYSTEM = """\
You match companies to the line of an investment thesis they belong under.

Reply with the line copied exactly as given, or null when none of them fits.
Never invent a line: an invented one creates a division nobody wrote.
"""


def main() -> int:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 400

    judge = create_openai_compatible_judge()
    done = skipped = 0

    with closing(connect()) as connection:
        for thesis in load_all_theses():
            rows = connection.execute(
                """
                SELECT accession, company_name, summary, reason
                FROM candidate
                WHERE theme = ? AND (subdomain IS NULL OR subdomain = '')
                  AND COALESCE(user_verdict, verdict) IN ('fits', 'maybe')
                ORDER BY filed_date DESC LIMIT ?
                """,
                (thesis.domain, limit),
            ).fetchall()

            if not rows:
                continue

            print(f"\n{thesis.domain}: {len(rows)} to place")

            lines = "\n".join(f'  - "{line}"' for line in thesis.include)

            for start in range(0, len(rows), BATCH):
                batch = rows[start : start + BATCH]

                blocks = "\n\n".join(
                    f"{index}. {row['company_name']}\n   "
                    + " ".join(
                        part for part in (row["summary"], row["reason"]) if part
                    )[:260]
                    for index, row in enumerate(batch, start=1)
                )

                prompt = (
                    f"Thesis: {thesis.name}\n\nLooking for:\n{lines}\n\n"
                    f"--- Companies ---\n\n{blocks}\n\n--- Answer ---\n\n"
                    'Reply with JSON only: {"1": "the line, copied exactly", ...}\n'
                )

                try:
                    raw = judge(SYSTEM, prompt)
                    body = raw[raw.find("{") : raw.rfind("}") + 1]
                    answer = json.loads(body)
                except Exception as exc:  # noqa: BLE001
                    print(f"  batch failed: {str(exc)[:60]}")
                    skipped += len(batch)
                    continue

                for index, row in enumerate(batch, start=1):
                    line = matched_line(answer.get(str(index)), thesis)

                    if not line:
                        skipped += 1
                        continue

                    connection.execute(
                        "UPDATE candidate SET subdomain = ? WHERE accession = ? "
                        "AND theme = ?",
                        (line, row["accession"], thesis.domain),
                    )
                    done += 1

                    print(f"  {row['company_name'][:30]:32} {line[:44]}")

                connection.commit()

    print(f"\nplaced {done}, unplaced {skipped}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
