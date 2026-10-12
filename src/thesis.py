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

from src.models import SEC_HEALTHCARE_GROUPS, FormDFiling


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

    # A short label — "Healthcare", "Finance", "Chips". This is what gets stored
    # on each judgement and shown in the domain dropdown, kept separate from
    # `name` because "Healthcare AI and clinical software" is a description and
    # makes a poor menu item.
    domain: str = Field(min_length=1, max_length=40)

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    include: list[str] = Field(min_length=1)
    exclude: list[str] = Field(default_factory=list)
    filters: ThesisFilters = Field(default_factory=ThesisFilters)

    # Which SEC industry groups to search. A thesis decision rather than a
    # technical one: healthcare software files under Technology, so a thesis
    # about healthcare software has to look there.
    sec_industry_groups: list[str] = Field(
        default_factory=lambda: list(SEC_HEALTHCARE_GROUPS)
    )

    # Whether visitors to the public site may see this domain and its
    # judgements. The owner always can.
    public: bool = True


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


def thesis_files(directory: Path | None = None) -> list[Path]:
    """Every thesis file on disk. One file per domain."""
    folder = directory or DEFAULT_THESIS_PATH.parent

    if not folder.exists():
        return []

    return sorted(folder.glob("*.yaml"))


def available_themes(directory: Path | None = None) -> list[str]:
    """
    Short domain labels from the thesis files, whether or not they have run.

    The dropdown reads these as well as the themes present in stored judgements.
    Data alone is not enough: a domain configured this morning has judged nothing
    yet, and leaving it out of the list makes it look like it does not exist. An
    unreadable file is skipped rather than breaking the whole list.
    """
    names: list[str] = []

    for path in thesis_files(directory):
        try:
            names.append(load_thesis(path).domain)
        except (ThesisError, Exception):  # noqa: BLE001
            continue

    return sorted(set(names))


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


# A domain name becomes a filename, so it has to survive being one. Letters,
# digits, spaces and hyphens only — no dots, no slashes, nothing that could walk
# out of the config directory.
SAFE_DOMAIN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 \-&]{0,39}$")


def thesis_filename(domain: str) -> str:
    """The file a domain lives in. Lowercase, hyphenated, no surprises."""
    slug = re.sub(r"[^a-z0-9]+", "-", domain.strip().lower()).strip("-")

    return f"{slug or 'thesis'}.yaml"


def find_thesis_path(domain: str, directory: Path | None = None) -> Path | None:
    """
    Where a domain's criteria are stored, if they are.

    Matched on the domain inside each file rather than the filename, because the
    original healthcare thesis lives in thesis.yaml and renaming it would break
    every command anyone has written down.
    """
    for path in thesis_files(directory):
        try:
            if load_thesis(path).domain == domain:
                return path
        except Exception:  # noqa: BLE001 - an unreadable file is not a match
            continue

    return None


def save_thesis(
    thesis: Thesis,
    directory: Path | None = None,
    original_domain: str | None = None,
) -> Path:
    """
    Write a thesis to disk, replacing the file it already lives in.

    Validation has already happened by the time a Thesis object exists, which is
    the point of taking one rather than a dict — a malformed edit cannot reach
    the file, and the daily run cannot be broken from a browser.

    Written to a temporary file and renamed, so a run reading the directory
    mid-save sees either the old file or the new one, never half of either.
    """
    if not SAFE_DOMAIN.match(thesis.domain):
        raise ThesisError(
            f"{thesis.domain!r} is not a usable domain name — letters, digits, "
            "spaces and hyphens only"
        )

    folder = directory or DEFAULT_THESIS_PATH.parent
    folder.mkdir(parents=True, exist_ok=True)

    # Creating and editing are different questions, and conflating them meant a
    # second thesis with an existing name silently overwrote the first instead
    # of being refused.
    if original_domain:
        path = find_thesis_path(original_domain, folder)

        if path is None:
            raise ThesisError(f"there is no thesis for {original_domain!r} to edit")

        if thesis.domain != original_domain:
            if find_thesis_path(thesis.domain, folder) is not None:
                raise ThesisError(f"a thesis for {thesis.domain!r} already exists")
    else:
        if find_thesis_path(thesis.domain, folder) is not None:
            raise ThesisError(f"a thesis for {thesis.domain!r} already exists")

        path = folder / thesis_filename(thesis.domain)

    body = yaml.safe_dump(
        thesis.model_dump(mode="json"),
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=80,
    )

    header = (
        f"# {thesis.name}\n"
        "#\n"
        "# Edited from the website. Everything here is plain text on purpose —\n"
        "# what reaches an inbox should be arguable without touching code.\n\n"
    )

    temporary = path.with_suffix(".yaml.tmp")
    temporary.write_text(header + body, encoding="utf-8")
    temporary.replace(path)

    return path


def delete_thesis(domain: str, directory: Path | None = None) -> bool:
    """
    Remove a domain's criteria.

    Judgements already made under it are left alone. They are a record of what
    was decided and when, and deleting them because the criteria changed would
    be erasing history to tidy a menu.
    """
    path = find_thesis_path(domain, directory)

    if path is None:
        return False

    path.unlink()

    return True


def load_all_theses(directory: Path | None = None) -> list[Thesis]:
    """Every readable thesis on disk, by domain."""
    loaded: list[Thesis] = []

    for path in thesis_files(directory):
        try:
            loaded.append(load_thesis(path))
        except Exception:  # noqa: BLE001 - one bad file is not all of them
            continue

    return sorted(loaded, key=lambda t: t.domain)
