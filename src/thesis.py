"""
The thesis: what counts as interesting, and the cheap filters applied first.

Ordering matters here. Threshold and pattern checks are free, and enrichment and
judgement both cost money, so nothing is looked up or scored until the
deterministic filters have had their say.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from src.models import FormDFiling


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_THESIS_PATH = PROJECT_ROOT / "config" / "thesis.yaml"


class ThesisFilters(BaseModel):
    """Deterministic rules that need no model and no network."""

    min_offering_amount: int = Field(default=0, ge=0)
    exclude_amendments: bool = True
    exclude_name_patterns: list[str] = Field(default_factory=list)

    # Form D permits an indefinite offering amount, so plenty of real companies
    # disclose nothing. Dropping those would be treating absence of evidence as
    # evidence of a nominal raise. In a radar a missed company costs more than
    # an extra one, so undisclosed amounts pass unless this is turned on.
    require_disclosed_amount: bool = False


class Thesis(BaseModel):
    """What the radar is looking for."""

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    include: list[str] = Field(min_length=1)
    exclude: list[str] = Field(default_factory=list)
    filters: ThesisFilters = Field(default_factory=ThesisFilters)


class ThesisError(RuntimeError):
    """Raised when the thesis cannot be read."""


def load_thesis(path: Path | None = None) -> Thesis:
    """Read and validate the thesis file."""
    location = path or DEFAULT_THESIS_PATH

    if not location.exists():
        raise ThesisError(f"no thesis file at {location}")

    try:
        raw = yaml.safe_load(location.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ThesisError(f"{location.name} is not valid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise ThesisError(f"{location.name} should contain a mapping")

    return Thesis.model_validate(raw)


def matches_excluded_name(name: str, patterns: list[str]) -> bool:
    """
    Whether a company name matches an excluded pattern.

    Matched on word boundaries so that "Fund" excludes "Acme Fund I" without
    also excluding "Fundamental Health" — substring matching here would quietly
    discard real companies.
    """
    lowered = name.lower()

    for pattern in patterns:
        cleaned = pattern.strip().lower()

        if not cleaned:
            continue

        if re.search(rf"(?<![a-z0-9]){re.escape(cleaned)}(?![a-z0-9])", lowered):
            return True

    return False


def rejection_reason(filing: FormDFiling, thesis: Thesis) -> str | None:
    """
    Why a filing fails the deterministic filters, or None if it passes.

    Returning the reason rather than a boolean means a digest can report what it
    dropped and why, instead of silently shrinking.
    """
    filters = thesis.filters

    if filters.exclude_amendments and filing.is_amendment:
        return "amendment — restates a round already reported"

    if matches_excluded_name(filing.company_name, filters.exclude_name_patterns):
        return "name suggests an investment vehicle, not an operating company"

    amount = filing.total_offering_amount

    if amount is None:
        if filters.require_disclosed_amount:
            return "no offering amount disclosed"

        # Indefinite offerings are common and legitimate. Let it through and
        # let the judging step decide on what the company actually does.
        return None

    if filters.min_offering_amount > 0 and amount < filters.min_offering_amount:
        return (
            f"offering of ${amount:,} is below the "
            f"${filters.min_offering_amount:,} floor"
        )

    return None


def apply_filters(
    filings: list[FormDFiling],
    thesis: Thesis,
) -> tuple[list[FormDFiling], list[tuple[FormDFiling, str]]]:
    """
    Split filings into those worth enriching and those dropped, with reasons.
    """
    kept: list[FormDFiling] = []
    dropped: list[tuple[FormDFiling, str]] = []

    for filing in filings:
        reason = rejection_reason(filing, thesis)

        if reason is None:
            kept.append(filing)
        else:
            dropped.append((filing, reason))

    return kept, dropped


def describe_for_prompt(thesis: Thesis) -> str:
    """
    Render the thesis as text for the judging step.

    Built from the same file a human reads, so there is one definition of the
    thesis rather than a document and a prompt that drift apart.
    """
    include = "\n".join(f"- {item}" for item in thesis.include)
    exclude = "\n".join(f"- {item}" for item in thesis.exclude)

    sections = [
        f"Thesis: {thesis.name}",
        "",
        thesis.description.strip(),
        "",
        "In scope:",
        include,
    ]

    if exclude:
        sections.extend(["", "Out of scope:", exclude])

    return "\n".join(sections)


if __name__ == "__main__":
    loaded = load_thesis()

    print(describe_for_prompt(loaded))
    print()
    print("filters:", loaded.filters.model_dump())
