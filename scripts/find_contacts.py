"""
Look for a contact address on each company's own website.

Fetches the homepage and, if that yields nothing, the contact and about pages.
Keeps an address only when its domain matches the company's own — without that
rule you collect the website builder's support desk, the PR agency, and every
npm package version on the page.

    .venv/bin/python scripts/find_contacts.py [limit]

Free. No model, no search API. Safe to re-run: only companies without an address
already stored are visited.
"""

from __future__ import annotations

import sys
import time
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.candidates import save_contact_email  # noqa: E402
from src.contact import create_page_fetcher, find_contact_email  # noqa: E402
from src.seen import connect  # noqa: E402


# Someone else's server. One request a second is polite and costs nothing here.
DELAY_SECONDS = 1.0


def main() -> int:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 100

    fetch = create_page_fetcher()
    found = missing = 0

    with closing(connect()) as connection:
        rows = connection.execute(
            """
            SELECT accession, company_name, website
            FROM candidate
            WHERE website IS NOT NULL AND website != ''
              AND (contact_email IS NULL OR contact_email = '')
            ORDER BY
                CASE COALESCE(user_verdict, verdict)
                    WHEN 'fits' THEN 0 WHEN 'maybe' THEN 1 ELSE 2
                END,
                filed_date DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        print(f"{len(rows)} companies with a website and no address yet")

        for row in rows:
            time.sleep(DELAY_SECONDS)

            email = find_contact_email(row["website"], fetch=fetch)

            if email:
                save_contact_email(connection, row["accession"], email)
                found += 1
                print(f"  {row['company_name'][:32]:34} {email}")
            else:
                missing += 1

    print(f"\nfound {found}, nothing on {missing}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
