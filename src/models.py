from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from src.normalize import normalize_company_name, slugify_company_name


# The five industry groups the SEC files under Health Care.
#
# A caution learned from real filings: these are NOT where healthcare software
# lives. Ambience Healthcare, Viz.ai and Nabla all filed under "Other
# Technology". The healthcare groups are mostly devices, therapeutics, clinical
# services, and occasionally a real-estate LLC. Which groups to actually search
# is a thesis decision and lives in config/thesis.yaml.
SEC_HEALTHCARE_GROUPS = (
    "Biotechnology",
    "Health Insurance",
    "Hospitals & Physicians",
    "Other Health Care",
    "Pharmaceuticals",
)


class RelatedPerson(BaseModel):
    """
    An officer, director, or promoter named on a Form D.

    Directors with an address far from the company's own are often the
    investor's board seat rather than an employee, which is a useful signal
    about who backed the round.
    """

    first_name: str = ""
    last_name: str = ""
    relationships: list[str] = Field(default_factory=list)
    city: str | None = None
    state: str | None = None

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class FormDFiling(BaseModel):
    """
    One Form D filing, as parsed from EDGAR.

    Note what is absent: a website, and any description of what the company
    does. A Form D says who raised money and how much, not what they build.
    Everything downstream of this needs enrichment.
    """

    accession: str = Field(min_length=1)
    cik: str = Field(min_length=1)
    company_name: str = Field(min_length=1)
    filed_date: str = Field(min_length=1)
    industry_group: str = Field(min_length=1)

    entity_type: str | None = None
    jurisdiction: str | None = None
    year_of_incorporation: int | None = Field(default=None, ge=1800, le=2100)
    city: str | None = None
    state: str | None = None

    total_offering_amount: int | None = Field(default=None, ge=0)
    total_amount_sold: int | None = Field(default=None, ge=0)
    investor_count: int | None = Field(default=None, ge=0)

    # The smallest cheque the company will take. Says who the round is built
    # for in one number: a $1,000 floor is friends and family, $50,000 is
    # angels, $250,000 is institutions only.
    minimum_investment: int | None = Field(default=None, ge=0)

    # When money first moved, which is not the filing date. A round can be
    # filed a year after it opened, and until you compare the two every
    # company in the digest looks equally new.
    first_sale_date: str | None = None

    is_amendment: bool = False
    related_persons: list[RelatedPerson] = Field(default_factory=list)

    @field_validator("company_name", mode="before")
    @classmethod
    def strip_name(cls, value: str) -> str:
        if isinstance(value, str):
            value = value.strip()

        if not value:
            raise ValueError("company_name cannot be empty")

        return value

    @property
    def canonical_name(self) -> str:
        """The identity key used for deduplication."""
        return normalize_company_name(self.company_name)

    @property
    def slug(self) -> str:
        """A readable identifier for paths and URLs."""
        return slugify_company_name(self.company_name)

    def in_groups(self, groups: list[str] | tuple[str, ...]) -> bool:
        """
        Whether the filing's own stated group is one being searched.

        Needed because full-text search matches a phrase anywhere in the
        document, so a search can return a filing that states a different group.
        The parsed field is authoritative; the search match is a hint.
        """
        return self.industry_group in tuple(groups)

    @property
    def is_newly_incorporated(self) -> bool:
        """
        Whether the company was formed recently relative to this filing.

        A company incorporated the same year it raises is at the earliest
        possible stage, which is the most interesting case for a radar.
        """
        if self.year_of_incorporation is None:
            return False

        try:
            filed_year = int(self.filed_date[:4])
        except (ValueError, IndexError):
            return False

        return filed_year - self.year_of_incorporation <= 1


class SeenCompany(BaseModel):
    """A company already surfaced, so it is never shown as new again."""

    canonical_name: str = Field(min_length=1)
    company_name: str = Field(min_length=1)
    canonical_domain: str | None = None
    first_seen: str = Field(min_length=1)
    source: str = Field(min_length=1)
    accession: str | None = None


# Four verdicts, not three. "maybe" and "unknown" were the same bucket, and in
# real data twelve of twenty maybes turned out to mean "we could not find out"
# rather than "this could go either way". Collapsing those fills a digest with
# shrugs, which is the fastest way to make a daily read stop being read.
FitVerdict = Literal["fits", "maybe", "unknown", "no_fit"]

# What kind of business this is, separate from whether it fits.
#
# A fixed list rather than free text, because the whole value is in counting:
# "emergency department software", "ED workflow" and "emergency dept coordination"
# are one category to a human and three to a GROUP BY. A closed vocabulary means
# the fifth one actually reads as the fifth.
#
# Drawn from what the real data contains. Four of the first eight companies that
# fit were clinical workflow, and four of the rejections were drug molecules —
# categories nobody would have guessed in advance but which the filings insist on.
CompanyCategory = Literal[
    # Inside the current thesis
    "clinical workflow",
    "ehr and documentation",
    "diagnostics and imaging",
    "virtual care",
    "patient engagement",
    "health data and analytics",
    "ai infrastructure",
    # Healthcare, but not software
    "drug development",
    "medical devices",
    "life sciences tools",
    "healthcare services",
    # Everything the Technology sweep drags in
    "not healthcare",
    "unclear",
]

CATEGORIES: tuple[str, ...] = (
    "clinical workflow",
    "ehr and documentation",
    "diagnostics and imaging",
    "virtual care",
    "patient engagement",
    "health data and analytics",
    "ai infrastructure",
    "drug development",
    "medical devices",
    "life sciences tools",
    "healthcare services",
    "not healthcare",
    "unclear",
)


class Candidate(BaseModel):
    """
    A filing that survived deduplication, once judged against the thesis.

    The verdict, reason and summary come from a model; everything else is from
    the filing. Keeping them in one object makes it obvious which fields are
    asserted by software and which are an opinion.
    """

    filing: FormDFiling
    verdict: FitVerdict
    reason: str = Field(min_length=1)
    category: CompanyCategory = "unclear"

    # What the company does, in one line. Distinct from `reason`, which explains
    # the verdict. A detail view needs the former and the digest needs the
    # latter, and a search snippet is a poor substitute for either.
    summary: str | None = None

    website: str | None = None
    description: str | None = None
