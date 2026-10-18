"""
What a visitor may see, enforced where the data is read rather than page by page.

The site is public to read. Visitors browse the judgements, the reasons and the
analysis; only the owner changes anything or spends money. Two kinds of thing
stay private even from reading:

- whole domains marked `public: false` in their criteria, and
- the owner's own working record on every company: their verdict where it
  overrules the model, their note, who they contacted, and what they have read.

Filtering each endpoint separately would mean every new endpoint is a fresh
chance to forget. Instead a visitor's connection sees temporary views that
shadow the real tables. SQLite resolves an unqualified table name to the temp
schema first, so every existing query reads the filtered rows without changing,
and a view cannot be written to, so nothing a visitor triggers can store
anything either.

Who is asking arrives as a header from the website's proxy, which sets it on
every request and overwrites whatever a client sent. The API itself listens only
on localhost, behind that proxy; a request with no header is a local script or
test, and is the owner.
"""

from __future__ import annotations

import sqlite3
from contextvars import ContextVar

from src.thesis import load_all_theses


VIEWER_HEADER = "x-radar-viewer"

# An anonymous id the proxy keeps in a cookie for each visitor, so the domains a
# visitor writes come back to them and to nobody else. See src/visitors.py.
VISITOR_HEADER = "x-radar-visitor-id"

# Owner: signed in. Reader: someone else's program holding an API token, which
# reads everything. Public: anyone else.
VIEWERS = ("owner", "reader", "public")

_viewer: ContextVar[str] = ContextVar("viewer", default="owner")
_visitor: ContextVar[str | None] = ContextVar("visitor", default=None)

# The owner's own record on a company. A visitor sees the model's verdict and
# reasoning, never these.
PRIVATE_COLUMNS = (
    "user_verdict",
    "user_note",
    "decided_at",
    "contact_email",
    "outreach_status",
    "outreach_at",
    "viewed_at",
)


def set_viewer(value: str | None):
    """Record who is asking for the rest of this request. Returns a reset token."""
    return _viewer.set(value if value in VIEWERS else "owner")


def reset_viewer(token) -> None:
    _viewer.reset(token)


def set_visitor(value: str | None):
    """Record which visitor is asking, if the id is well formed. Returns a token."""
    from src.visitors import valid_id

    return _visitor.set(valid_id(value))


def reset_visitor(token) -> None:
    _visitor.reset(token)


def visitor_id() -> str | None:
    """The visitor's anonymous id, or None for the owner, a reader, or no cookie."""
    return _visitor.get() if is_public() else None


def viewer() -> str:
    return _viewer.get()


def is_public() -> bool:
    return viewer() == "public"


def private_domains() -> list[str]:
    """Domains whose criteria say they are not for visitors."""
    return [thesis.domain for thesis in load_all_theses() if not thesis.public]


def visible(domains: list[str]) -> list[str]:
    """The domains this viewer may see."""
    if not is_public():
        return domains

    hidden = set(private_domains())

    return [domain for domain in domains if domain not in hidden]


def quoted(value: str) -> str:
    """A string literal for SQL. Views cannot take bound parameters."""
    return "'" + value.replace("'", "''") + "'"


def apply_public_view(
    connection: sqlite3.Connection,
    hidden: list[str],
    visitor: str | None = None,
) -> None:
    """
    Shadow the judgement tables with what a visitor may read.

    `candidate` loses the hidden domains' rows and the owner's columns, and gains
    this visitor's own judgements, if they have written any domains. The tables
    keyed by filing follow it, so a person or a researcher found only on a hidden
    domain's company is not listed either.
    """
    columns = [
        row["name"]
        for row in connection.execute("PRAGMA main.table_info(candidate)")
    ]
    select = ", ".join(
        f"NULL AS {name}" if name in PRIVATE_COLUMNS else name for name in columns
    )
    where = (
        f"WHERE theme IS NULL OR theme NOT IN ({', '.join(quoted(d) for d in hidden)})"
        if hidden
        else ""
    )

    # The visitor's own rows. visitor_candidate mirrors candidate's columns, and
    # the owner's ones are stored empty there, so they can be selected as they are.
    mine = (
        f"UNION ALL SELECT {', '.join(columns)} FROM main.visitor_candidate "
        f"WHERE visitor_id = {quoted(visitor)}"
        if visitor
        else ""
    )

    connection.executescript(
        f"""
        CREATE TEMP VIEW candidate AS
            SELECT {select} FROM main.candidate {where} {mine};
        CREATE TEMP VIEW person AS SELECT * FROM main.person
            WHERE accession IN (SELECT accession FROM temp.candidate);
        CREATE TEMP VIEW researcher AS SELECT * FROM main.researcher
            WHERE accession IN (SELECT accession FROM temp.candidate);
        CREATE TEMP VIEW momentum_signal AS SELECT * FROM main.momentum_signal
            WHERE ltrim(cik, '0') IN (
                SELECT ltrim(cik, '0') FROM temp.candidate WHERE cik IS NOT NULL
            );
        """
    )
