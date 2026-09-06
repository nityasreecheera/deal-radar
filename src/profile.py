"""
A written explanation of what a company is.

Enrichment keeps whatever the web search returned, which for most companies is
their homepage marketing: section headings with no sections under them, a
truncation marker where the crawler gave up, the same phrase twice because it
appears twice in the layout, and occasionally the name of a background graphic.
Putting that on the page unedited asks the reader to do the work the radar exists
to do.

This turns it into prose a person can read: what the company does, who buys it,
and how it works, in that order. It is written once per company, on the first
request, and kept — so the cost is one call for each company actually opened
rather than one for every company ever judged.

The model is given the scraped text and the filing and told to write only from
them. If it is unreachable, nothing is written and the caller falls back to the
scraped text cleaned up. A page that quietly invents a company profile when the
lookup failed would be the same mistake as a digest reporting a quiet day.
"""

from __future__ import annotations

import re

from src.chat import ChatFunction, create_chat_client


class Unavailable(RuntimeError):
    """The model could not be reached, so nothing was written."""


SYSTEM_PROMPT = """\
You explain what a company does, for an investor reading quickly.

You are given a company's SEC filing details and whatever text was scraped from
its website. Write three short paragraphs, no headings, no bullet points:

1. What the company sells, in one or two plain sentences. No adjectives from
   their marketing — "AI-powered", "cutting-edge", "seamless" and similar go.
2. Who buys it and what problem it solves for them.
3. How it works, as far as the text says. If the text does not say, write that
   the material does not explain how it works, and stop.

Rules:
- Use only the material given. Never add a fact you were not told, however
  plausible — no market sizes, no competitors, no funding history.
- The scraped text is the company's own marketing. Report claims as claims:
  "they say", "according to their site". Never assert a savings figure or a
  customer as established fact.
- If the material is too thin to explain the company, say exactly that in one
  sentence rather than padding.
- Plain English. Someone outside the sector should follow it.
"""

# Marketing pages scrape badly in consistent ways.
NOISE = (
    # Headings with nothing under them. Matched mid-line too, because the scrape
    # arrives with its newlines already flattened into spaces, so the markers sit
    # in the middle of one long line rather than at the start of theirs.
    (re.compile(r"(?:^|(?<=\s))#{1,6}\s*", re.M), ""),
    (re.compile(r"\[\.\.\.\]"), " "),              # the crawler's truncation marker
    (re.compile(r"\s*\|\s*"), " "),                # nav bars flattened into pipes
    (re.compile(r"[ \t]+"), " "),
    (re.compile(r"\n{3,}"), "\n\n"),
)


def tidy(text: str | None) -> str:
    """
    Make scraped text readable without changing what it says.

    Only removes artefacts of scraping — markup, truncation markers, and phrases
    the layout repeated. Nothing is summarised or reworded here, because this is
    also the fallback shown when the model is unavailable, and a fallback that
    edits meaning is worse than the mess it replaces.
    """
    if not text:
        return ""

    cleaned = text

    for pattern, replacement in NOISE:
        cleaned = pattern.sub(replacement, cleaned)

    # "Multi-Objective Optimization Multi-Objective Optimization" is one heading
    # rendered twice by a responsive layout, not emphasis.
    cleaned = re.sub(r"\b(.{6,60}?)\s+\1\b", r"\1", cleaned)

    return cleaned.strip()


def build_prompt(
    company_name: str,
    summary: str | None,
    description: str | None,
    website: str | None,
    industry_group: str | None,
    amount: int | None,
) -> str:
    raised = f"${amount:,}" if amount else "not disclosed"

    return f"""\
Company: {company_name}
Website: {website or "not found"}
SEC industry group: {industry_group or "not stated"}
Raising: {raised}

One-line summary on record: {summary or "none"}

Text scraped from their site:
\"\"\"
{tidy(description) or "(nothing was scraped)"}
\"\"\"
"""


def write_profile(
    company_name: str,
    summary: str | None = None,
    description: str | None = None,
    website: str | None = None,
    industry_group: str | None = None,
    amount: int | None = None,
    chat: ChatFunction | None = None,
) -> str:
    """
    Write the explanation. Raises `Unavailable` rather than returning a guess.
    """
    if not tidy(description) and not summary:
        raise Unavailable("nothing was found about this company to explain")

    responder = chat or create_chat_client()

    try:
        reply = responder(
            SYSTEM_PROMPT,
            build_prompt(
                company_name, summary, description, website, industry_group, amount
            ),
        )
    except Exception as exc:  # noqa: BLE001 — any failure means no profile, not a bad one
        raise Unavailable(str(exc)) from exc

    text = (reply or "").strip()

    if not text:
        raise Unavailable("the model returned nothing")

    return text
