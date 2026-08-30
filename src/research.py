"""
Whether the people on a filing have a research record.

For a company nobody has heard of, the founders' published work is sometimes the
only evidence that exists — and for a nuclear or drug-discovery company it can be
the most telling thing available. OrganiCore Nuclear's filing names Koroush
Shirvan, who has 247 papers on reactor physics. That says more than the raise
does.

OpenAlex is free, needs no key, and asks only that you identify yourself.

The hard part is not finding a record, it is refusing the wrong one. Searching
"Alonso Galvan" returns a Spanish hospital oncologist, and Cornelis Networks
makes networking hardware in Pennsylvania. Two defences:

  - a record has to be substantial before it is considered at all, which removes
    the one-and-two-paper namesakes that make up most false matches;
  - the research field has to plausibly belong to somebody founding this
    particular company, which is a judgement, so a model makes it.

Even then it is reported as a possible match with the field and institution
shown, never as a fact. A confident wrong attribution about a real person is
worse than saying nothing.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Callable

from pydantic import BaseModel, Field


CONTACT = "nityasree.cheera24@gmail.com"
OPENALEX = "https://api.openalex.org/authors"

# Below this, a match is far more likely to be a namesake than the founder.
# Every false match in testing had fewer than five works; the true one had 247.
MIN_WORKS = 10

# How many candidates to weigh per name. Beyond the first few the search is
# reaching, and each one costs a judgement.
MAX_CANDIDATES = 3


class Researcher(BaseModel):
    """An academic record that might belong to somebody on a filing."""

    name: str
    openalex_id: str = ""
    works: int = 0
    citations: int = 0
    institution: str = ""
    topics: list[str] = Field(default_factory=list)

    # Whether the field plausibly belongs to somebody founding this company.
    # Never asserted as identity — this says the record is worth showing, not
    # that it is definitely the same person.
    plausible: bool = False

    @property
    def summary(self) -> str:
        parts = [f"{self.works} papers"]

        if self.citations:
            parts.append(f"{self.citations:,} citations")

        if self.topics:
            parts.append(self.topics[0].lower())

        return ", ".join(parts)


def create_lookup(contact: str | None = None) -> Callable[[str], list[dict]]:
    """A function that searches OpenAlex by name."""
    mailto = contact or CONTACT

    def lookup(name: str) -> list[dict]:
        url = (
            f"{OPENALEX}?search={urllib.parse.quote(name)}"
            f"&per-page={MAX_CANDIDATES}&mailto={mailto}"
        )
        request = urllib.request.Request(
            url, headers={"User-Agent": f"deal-radar ({mailto})"}
        )

        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response).get("results", [])

    return lookup


def parse_author(payload: dict) -> Researcher:
    """One OpenAlex author, as much of it as is worth keeping."""
    institutions = payload.get("last_known_institutions") or []

    return Researcher(
        name=payload.get("display_name", ""),
        openalex_id=payload.get("id", ""),
        works=payload.get("works_count", 0) or 0,
        citations=payload.get("cited_by_count", 0) or 0,
        institution=(institutions[0].get("display_name", "") if institutions else ""),
        topics=[
            topic.get("display_name", "")
            for topic in (payload.get("topics") or [])[:3]
            if topic.get("display_name")
        ],
    )


def candidates_for(
    name: str,
    lookup: Callable[[str], list[dict]] | None = None,
) -> list[Researcher]:
    """
    Research records substantial enough to be worth weighing.

    The threshold does most of the work. A founder with a real academic career
    has dozens of papers; a namesake who once appeared on a case report has one.
    """
    if not name or not name.strip():
        return []

    finder = lookup or create_lookup()

    try:
        results = finder(name)
    except Exception:  # noqa: BLE001 - a missing record is not an error
        return []

    found = [parse_author(item) for item in results]

    return [r for r in found if r.works >= MIN_WORKS]


PLAUSIBILITY_PROMPT = """\
You are checking whether a research record belongs to a company's founder, or to
somebody who merely shares their name.

Answer only on whether the research field plausibly belongs to a person founding
this company. A nuclear engineer founding a nuclear company is plausible. An
oncologist named on a networking hardware company is not — that is a namesake.

Be strict. A wrong attribution about a real person is worse than saying nothing.
"""


class Unavailable(RuntimeError):
    """The judgement could not be made — not the same as a no."""


def check_plausible(
    researcher: Researcher,
    company_name: str,
    company_does: str,
    judge: Callable[[str, str], str],
) -> bool:
    """
    Whether this record plausibly belongs to somebody at this company.

    A judgement, so the model makes it — the same division as everywhere else
    here. The mechanics of finding and filtering are code; whether nuclear
    physics belongs at a nuclear company is not.

    Raises Unavailable when the model cannot be reached, rather than returning
    False. An earlier version caught everything and answered no, so an account
    out of credit produced "checked 40, plausible matches 0" — a finding nobody
    made, and indistinguishable from having genuinely checked.
    """
    prompt = (
        f"Company: {company_name}\n"
        f"What it does: {company_does or 'unknown'}\n\n"
        f"Person: {researcher.name}\n"
        f"Institution: {researcher.institution or 'unknown'}\n"
        f"Research fields: {', '.join(researcher.topics) or 'unknown'}\n"
        f"Papers: {researcher.works}\n\n"
        'Reply with JSON only: {"plausible": true or false}\n'
    )

    try:
        raw = judge(PLAUSIBILITY_PROMPT, prompt)
    except Exception as exc:  # noqa: BLE001 - the model, not the answer
        raise Unavailable(str(exc)) from exc

    try:
        body = raw[raw.find("{") : raw.rfind("}") + 1]

        # An unreadable answer *is* a no. Silence about a named person should
        # never become a claim about them.
        return bool(json.loads(body).get("plausible"))
    except Exception:  # noqa: BLE001
        return False
