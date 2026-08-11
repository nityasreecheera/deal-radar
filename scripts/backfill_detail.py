"""
Fill in filing detail for judgements recorded before it was stored.

Re-fetches each filing's XML from EDGAR and writes the officers, directors,
amount sold, investor count, jurisdiction, entity type, minimum cheque and
first-sale date onto the existing row.
The verdict and reason are left alone: they were reached on the evidence
available at the time, and rewriting them here would be inventing history.

Free to run — EDGAR needs no key, and this touches neither the model nor the
search API.
"""

from __future__ import annotations

import json
import sys
import time
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.edgar import (  # noqa: E402
    REQUEST_DELAY_SECONDS,
    EdgarError,
    create_fetcher,
    filing_xml_url,
    parse_form_d,
)
from src.seen import connect  # noqa: E402


def main() -> int:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 200

    fetch = create_fetcher()
    filled = 0
    failed = 0

    with closing(connect()) as connection:
        rows = connection.execute(
            """
            SELECT accession, company_name, cik, filed_date
            FROM candidate
            WHERE people IS NULL OR people = '' OR people = '[]'
               OR (first_sale_date IS NULL AND minimum_investment IS NULL)
            ORDER BY filed_date DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        print(f"{len(rows)} judgements missing detail")

        for row in rows:
            accession = row["accession"]

            # The SEC asks for no more than ten requests a second, and a few
            # hundred filings in a tight loop is how you get a 429 for the rest
            # of the run.
            time.sleep(REQUEST_DELAY_SECONDS)

            # The CIK on the row is present only if it was saved after that
            # column existed. Otherwise fall back to the accession prefix — but
            # note that prefix is the *filing agent's* CIK, not the issuer's, and
            # EDGAR stores the document under the issuer, so an agent-filed
            # submission 404s. Those cannot be recovered without the issuer CIK
            # and are reported rather than silently skipped.
            cik = row["cik"] or accession.split("-")[0]

            try:
                filing = parse_form_d(
                    fetch(filing_xml_url(cik, accession)),
                    accession,
                    row["filed_date"],
                )
            except (EdgarError, Exception) as exc:  # noqa: BLE001
                reason = str(exc).splitlines()[0][:70]
                print(f"  {row['company_name'][:34]:34} failed: {reason}")
                failed += 1
                continue

            connection.execute(
                """
                UPDATE candidate SET
                    people = ?, amount_sold = ?, investor_count = ?,
                    jurisdiction = ?, entity_type = ?, cik = ?,
                    minimum_investment = ?, first_sale_date = ?
                WHERE accession = ?
                """,
                (
                    json.dumps(
                        [p.model_dump(mode="json") for p in filing.related_persons]
                    ),
                    filing.total_amount_sold,
                    filing.investor_count,
                    filing.jurisdiction,
                    filing.entity_type,
                    filing.cik,
                    filing.minimum_investment,
                    filing.first_sale_date,
                    accession,
                ),
            )

            names = ", ".join(p.full_name for p in filing.related_persons[:3])
            print(f"  {filing.company_name[:36]:36} {names}")
            filled += 1

        connection.commit()

    print(f"\nfilled {filled}, failed {failed}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
