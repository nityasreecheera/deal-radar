"""
Fill in funding history and people rows for companies judged before either
existed.

Free to run. EDGAR needs no key, and this touches neither the model nor the
search API. It is one request per company for the filing index, plus one per
historical filing.

By default it only covers companies worth reading about, since there is no point
spending requests on rejections nobody opens.

Usage:
    python scripts/backfill_funding.py [limit] [--all]
"""

from __future__ import annotations

import json
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.funding import fetch_history, save_history  # noqa: E402
from src.models import RelatedPerson  # noqa: E402
from src.people import save_people  # noqa: E402
from src.seen import connect  # noqa: E402


def main() -> int:
    limit = 200
    include_rejections = "--all" in sys.argv

    for argument in sys.argv[1:]:
        if argument.isdigit():
            limit = int(argument)

    filled = 0
    failed = 0
    people_rows = 0

    with closing(connect()) as connection:
        # People first: this needs no network at all, since the names are
        # already stored as JSON on each row.
        for row in connection.execute(
            "SELECT accession, people FROM candidate WHERE people IS NOT NULL"
        ).fetchall():
            try:
                parsed = json.loads(row["people"] or "[]")
            except json.JSONDecodeError:
                continue

            people_rows += save_people(
                connection,
                row["accession"],
                [RelatedPerson(**person) for person in parsed],
            )

        print(f"people rows written: {people_rows}")

        clause = "" if include_rejections else " AND verdict != 'no_fit'"

        rows = connection.execute(
            f"""
            SELECT DISTINCT cik, company_name
            FROM candidate
            WHERE cik IS NOT NULL AND cik != '' AND cik != '0'{clause}
            ORDER BY filed_date DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        print(f"fetching funding history for {len(rows)} companies\n")

        for row in rows:
            try:
                history = fetch_history(row["cik"])
            except Exception as exc:  # noqa: BLE001
                print(f"  {row['company_name'][:32]:32} failed: {str(exc)[:44]}")
                failed += 1
                continue

            save_history(connection, history)
            filled += 1

            real = [r for r in history.rounds if not r.is_amendment]
            note = "first raise" if len(real) <= 1 else f"{len(real)} raises"
            print(f"  {row['company_name'][:32]:32} {note}")

    print(f"\nhistories filled {filled}, failed {failed}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
