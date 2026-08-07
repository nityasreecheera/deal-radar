"""
The people named on filings, and where else they turn up.

A Form D names officers, directors and promoters. Reading one filing that is mildly
interesting; reading across filings it is the most useful thing in the document,
because the same person appearing on two companies is either a serial founder or an
investor taking board seats.

An important limit: this only sees companies the radar has already collected. I
checked whether EDGAR's full-text search can find a person across all filings and
it cannot — the names in a Form D are not indexed, so searching "Eirini Schlosser"
returns nothing while "Schlosser" returns forty-three unrelated people. So this is
a join over our own data, and it gets more useful the longer the radar runs.
"""

from __future__ import annotations

import re
import sqlite3

from pydantic import BaseModel, Field

from src.models import RelatedPerson


class PersonLink(BaseModel):
    """Someone who appears on more than one company we have seen."""

    full_name: str = Field(min_length=1)
    relationships: list[str] = Field(default_factory=list)
    other_companies: list[str] = Field(default_factory=list)


def name_key(first_name: str, last_name: str) -> str:
    """
    A comparable form of a person's name.

    Lowercased with punctuation removed, so "O'Brien" and "OBrien" match. No
    attempt at nicknames or initials — treating "R. Smith" as "Robert Smith"
    would invent connections that are not in the data.
    """
    joined = f"{first_name or ''} {last_name or ''}".strip().lower()

    return re.sub(r"[^a-z0-9]+", "", joined)


def save_people(
    connection: sqlite3.Connection,
    accession: str,
    people: list[RelatedPerson],
) -> int:
    """Record the people on one filing. Returns how many were stored."""
    stored = 0

    for person in people:
        key = name_key(person.first_name, person.last_name)

        if not key:
            continue

        connection.execute(
            """
            INSERT INTO person (
                accession, name_key, full_name, relationships, city, state
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (accession, name_key) DO UPDATE SET
                relationships = excluded.relationships,
                city          = excluded.city,
                state         = excluded.state
            """,
            (
                accession,
                key,
                person.full_name,
                ", ".join(person.relationships),
                person.city,
                person.state,
            ),
        )
        stored += 1

    connection.commit()

    return stored


def shared_people(
    connection: sqlite3.Connection,
    accession: str,
) -> list[PersonLink]:
    """
    People on this filing who also appear on another company we have seen.

    Only returns someone when there is another company to point at. A person on
    one filing is not a connection, and listing them as one would make the
    feature look busy while saying nothing.
    """
    rows = connection.execute(
        """
        SELECT
            p.full_name,
            p.relationships,
            other.company_name
        FROM person p
        JOIN person q
            ON q.name_key = p.name_key
           AND q.accession != p.accession
        JOIN candidate other
            ON other.accession = q.accession
        WHERE p.accession = ?
        ORDER BY p.full_name, other.filed_date DESC
        """,
        (accession,),
    ).fetchall()

    grouped: dict[str, PersonLink] = {}

    for row in rows:
        link = grouped.setdefault(
            row["full_name"],
            PersonLink(
                full_name=row["full_name"],
                relationships=[
                    part.strip()
                    for part in (row["relationships"] or "").split(",")
                    if part.strip()
                ],
            ),
        )

        if row["company_name"] not in link.other_companies:
            link.other_companies.append(row["company_name"])

    return list(grouped.values())


def most_connected(
    connection: sqlite3.Connection,
    limit: int = 10,
) -> list[tuple[str, int]]:
    """
    People appearing on the most companies, most first.

    Useful as a standalone view: the names at the top of this list are usually
    either active investors or someone running several related entities.
    """
    rows = connection.execute(
        """
        SELECT full_name, COUNT(DISTINCT accession) AS n
        FROM person
        GROUP BY name_key
        HAVING n > 1
        ORDER BY n DESC, full_name ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    return [(row["full_name"], int(row["n"])) for row in rows]
