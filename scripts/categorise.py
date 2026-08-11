"""
Put a category on judgements recorded before categories existed.

Reads only what is already stored — the summary, the reason, the description —
and asks the model to sort each company into one of the fixed categories. It does
not re-enrich, which is the whole point: re-running enrichment would spend a web
search per company and burn a month's free tier to answer a question the stored
text already answers.

Companies are sent in batches because one round trip for fifteen companies costs
a fraction of fifteen round trips, and sorting into a fixed list needs far less
context than judging fit does.

    .venv/bin/python scripts/categorise.py [limit]

Safe to re-run. Only rows without a category are touched, and a verdict is never
altered — this describes what a company is, not whether it fits.
"""

from __future__ import annotations

import json
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.judge import create_openai_compatible_judge  # noqa: E402
from src.models import CATEGORIES  # noqa: E402
from src.seen import connect  # noqa: E402


BATCH_SIZE = 15

SYSTEM_PROMPT = """\
You sort companies into categories for an investment analyst.

Put each company into exactly one category from the list. The category describes
what kind of business it is, and is independent of whether anyone wants to invest
in it: a drug company is "drug development" whether it is interesting or not.

Use "not healthcare" freely. The search that found these deliberately casts a
wide net over technology filings, so a good number are animation studios, banks
and food companies that have nothing to do with health.

Use "unclear" only when the text genuinely does not say what the company does.
"""


def render(rows) -> str:
    """One numbered block per company, from what is already on the row."""
    blocks = []

    for index, row in enumerate(rows, start=1):
        evidence = " ".join(
            part
            for part in (
                row["summary"],
                row["reason"],
                (row["description"] or "")[:200],
            )
            if part
        )

        blocks.append(
            f"{index}. {row['company_name']}\n"
            f"   SEC industry: {row['industry_group'] or 'unknown'}\n"
            f"   What is known: {evidence[:400] or 'nothing'}"
        )

    return "\n\n".join(blocks)


def build_prompt(rows) -> str:
    categories = ", ".join(f'"{name}"' for name in CATEGORIES)

    return f"""\
Categories: {categories}

--- Companies ---

{render(rows)}

--- Answer ---

Reply with JSON only, one entry per company, using the numbers above:
{{"1": "category", "2": "category", ...}}
"""


def parse(raw: str, count: int) -> dict[int, str]:
    """Pull the mapping out, ignoring anything that is not a real category."""
    start, end = raw.find("{"), raw.rfind("}")

    if start == -1 or end == -1:
        return {}

    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return {}

    found: dict[int, str] = {}

    for key, value in data.items():
        try:
            index = int(str(key).strip())
        except ValueError:
            continue

        # A category outside the list is worse than none: it would fragment the
        # counting, which is the only reason the list is fixed.
        if 1 <= index <= count and value in CATEGORIES:
            found[index] = value

    return found


def main() -> int:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 500

    judge = create_openai_compatible_judge()
    done = skipped = 0

    with closing(connect()) as connection:
        rows = connection.execute(
            """
            SELECT accession, company_name, summary, reason, description,
                   industry_group
            FROM candidate
            WHERE category IS NULL OR category = ''
            ORDER BY filed_date DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        print(f"{len(rows)} judgements without a category")

        for start in range(0, len(rows), BATCH_SIZE):
            batch = rows[start : start + BATCH_SIZE]

            try:
                answer = parse(
                    judge(SYSTEM_PROMPT, build_prompt(batch)), len(batch)
                )
            except Exception as exc:  # noqa: BLE001 - one bad batch is not fatal
                print(f"  batch {start // BATCH_SIZE + 1} failed: {exc}")
                skipped += len(batch)
                continue

            for index, row in enumerate(batch, start=1):
                category = answer.get(index)

                if not category:
                    skipped += 1
                    continue

                connection.execute(
                    "UPDATE candidate SET category = ? WHERE accession = ?",
                    (category, row["accession"]),
                )
                done += 1

                print(f"  {row['company_name'][:34]:36} {category}")

            connection.commit()

    print(f"\ncategorised {done}, skipped {skipped}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
