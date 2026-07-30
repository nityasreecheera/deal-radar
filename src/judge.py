"""
Judging: does this company fit the thesis?

The only step where a model forms an opinion. Its output is validated before
anything is written, and it is told explicitly when the evidence it was given is
weak, so "not enough information" is an available answer rather than a guess.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable

import httpx
from pydantic import BaseModel, Field, ValidationError

from src.enrich import Enrichment
from src.models import Candidate, FitVerdict, FormDFiling
from src.thesis import Thesis, describe_for_prompt


PROJECT_ROOT = Path(__file__).resolve().parent.parent

# An OpenAI-compatible chat endpoint. OpenRouter is the default because the
# credential already exists on the machine that runs this; point base_url
# elsewhere and nothing else changes.
DEFAULT_BASE_URL = os.getenv(
    "LLM_BASE_URL",
    "https://openrouter.ai/api/v1",
)
DEFAULT_MODEL = os.getenv("LLM_MODEL", "anthropic/claude-sonnet-4.5")

SYSTEM_PROMPT = """\
You screen companies against an investment thesis for an analyst.

Decide whether a company fits, using only the evidence provided. Answer with one
of three verdicts:

  fits    — clearly within the thesis
  maybe   — plausibly within it, or the evidence is too thin to be sure
  no_fit  — clearly outside it

Rules that matter more than being decisive:

- Judge what the company does, not whether it sounds impressive.
- The evidence may be weak or absent. When it is, answer "maybe" and say what is
  missing. Never infer a business model from a company's name alone.
- A large raise is not evidence of fit. Neither is a well-known investor.
- Give one sentence of reasoning. An analyst reads dozens of these, so the
  reason must be specific: name the thing that decided it.
"""

# A judge takes the rendered prompt and returns raw model text.
JudgeFunction = Callable[[str, str], str]


class JudgementError(RuntimeError):
    """Raised when the model's answer cannot be used."""


class Judgement(BaseModel):
    """The model's verdict on one company."""

    verdict: FitVerdict
    reason: str = Field(min_length=1)

    @property
    def is_interesting(self) -> bool:
        return self.verdict in ("fits", "maybe")


def create_openai_compatible_judge(
    base_url: str | None = None,
    model: str | None = None,
) -> JudgeFunction:
    """Build a judge backed by an OpenAI-compatible chat endpoint."""
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")

    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("LLM_API_KEY")

    if not api_key:
        raise JudgementError(
            "No LLM key found. Set OPENROUTER_API_KEY (or LLM_API_KEY) in .env"
        )

    endpoint = (base_url or DEFAULT_BASE_URL).rstrip("/")
    chosen_model = model or DEFAULT_MODEL

    client = httpx.Client(
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=60.0,
    )

    def judge(system_prompt: str, user_prompt: str) -> str:
        response = client.post(
            f"{endpoint}/chat/completions",
            json={
                "model": chosen_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                # Low temperature: this is classification, not writing.
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
        )

        if response.status_code == 401:
            raise JudgementError("LLM endpoint rejected the API key (401)")

        response.raise_for_status()

        payload = response.json()

        try:
            return payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise JudgementError(f"unexpected response shape: {exc}") from exc

    return judge


def build_prompt(
    filing: FormDFiling,
    enrichment: Enrichment,
    thesis: Thesis,
) -> str:
    """
    Render everything known about a company into a prompt.

    The provenance of the description is stated plainly. A snippet from a
    directory listing is much weaker evidence than a company's own homepage, and
    the model cannot weigh that unless it is told.
    """
    people = ", ".join(
        f"{person.full_name} ({'/'.join(person.relationships) or 'unspecified'})"
        for person in filing.related_persons[:4]
    )

    amount = (
        f"${filing.total_offering_amount:,}"
        if filing.total_offering_amount is not None
        else "undisclosed"
    )

    if enrichment.description and enrichment.confident:
        evidence = (
            f"From the company's own site ({enrichment.website}):\n"
            f"{enrichment.description}"
        )
    elif enrichment.description:
        evidence = (
            "No company website could be identified. This description came from "
            "a third-party page, so treat it as weak evidence:\n"
            f"{enrichment.description}"
        )
    else:
        evidence = (
            "Nothing could be found about what this company does. Only the "
            "filing is available."
        )

    return f"""\
{describe_for_prompt(thesis)}

--- Company ---

Name: {filing.company_name}
SEC industry group: {filing.industry_group}
Location: {filing.city or "unknown"}, {filing.state or "unknown"}
Incorporated: {filing.year_of_incorporation or "unknown"}
Entity type: {filing.entity_type or "unknown"}
Offering: {amount}
People named on the filing: {people or "none listed"}

--- Evidence ---

{evidence}

--- Answer ---

Reply with JSON only:
{{"verdict": "fits" | "maybe" | "no_fit", "reason": "one specific sentence"}}
"""


def parse_judgement(raw: str) -> Judgement:
    """
    Validate the model's answer.

    A model asked for JSON sometimes wraps it in prose or a code fence, so the
    outermost braces are extracted before parsing. Anything that still fails
    validation is an error rather than a default verdict — silently defaulting
    would put an unexamined company in front of an analyst.
    """
    text = raw.strip()

    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end < start:
        raise JudgementError(f"no JSON object in the answer: {text[:120]!r}")

    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise JudgementError(f"answer was not valid JSON: {exc}") from exc

    try:
        return Judgement.model_validate(data)
    except ValidationError as exc:
        raise JudgementError(f"answer did not match the schema: {exc}") from exc


def judge_filing(
    filing: FormDFiling,
    enrichment: Enrichment,
    thesis: Thesis,
    judge: JudgeFunction | None = None,
) -> Candidate:
    """Judge one company and return it as a candidate."""
    judger = judge or create_openai_compatible_judge()

    prompt = build_prompt(filing, enrichment, thesis)
    judgement = parse_judgement(judger(SYSTEM_PROMPT, prompt))

    return Candidate(
        filing=filing,
        verdict=judgement.verdict,
        reason=judgement.reason,
        website=enrichment.website,
        description=enrichment.description,
    )
