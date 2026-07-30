from pathlib import Path

import pytest

from src.models import FormDFiling
from src.thesis import (
    Thesis,
    ThesisError,
    apply_filters,
    describe_for_prompt,
    load_thesis,
    matches_excluded_name,
    rejection_reason,
)


def filing(**overrides) -> FormDFiling:
    data = {
        "accession": "acc-1",
        "cik": "1",
        "company_name": "Acme Health, Inc.",
        "filed_date": "2026-07-27",
        "industry_group": "Other Health Care",
        "total_offering_amount": 5_000_000,
        "is_amendment": False,
    }
    data.update(overrides)

    return FormDFiling(**data)


def thesis(**overrides) -> Thesis:
    data = {
        "domain": "TestDomain",
        "name": "Test thesis",
        "description": "Healthcare software.",
        "include": ["clinical software"],
        "exclude": ["devices"],
        "filters": {
            "min_offering_amount": 500_000,
            "exclude_amendments": True,
            "exclude_name_patterns": ["fund", "ventures"],
        },
    }
    data.update(overrides)

    return Thesis.model_validate(data)


def test_the_real_thesis_file_is_valid() -> None:
    # The shipped config must parse, or the radar cannot run at all.
    loaded = load_thesis()

    assert loaded.name
    assert loaded.include
    assert loaded.filters.min_offering_amount > 0


def test_a_missing_thesis_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ThesisError, match="no thesis file"):
        load_thesis(tmp_path / "absent.yaml")


def test_invalid_yaml_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "thesis.yaml"
    path.write_text("name: [unclosed", encoding="utf-8")

    with pytest.raises(ThesisError, match="not valid YAML"):
        load_thesis(path)


def test_a_yaml_file_that_is_not_a_mapping_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "thesis.yaml"
    path.write_text("- just\n- a\n- list\n", encoding="utf-8")

    with pytest.raises(ThesisError, match="should contain a mapping"):
        load_thesis(path)


def test_excluded_names_match_on_word_boundaries() -> None:
    patterns = ["fund", "ventures"]

    assert matches_excluded_name("Acme Fund I, LP", patterns) is True
    assert matches_excluded_name("Redwood Ventures LLC", patterns) is True

    # The trap: substring matching would discard both of these real companies.
    assert matches_excluded_name("Fundamental Health, Inc.", patterns) is False
    assert matches_excluded_name("Adventures in Care Inc.", patterns) is False


def test_excluded_names_ignore_empty_patterns() -> None:
    assert matches_excluded_name("Anything", ["", "   "]) is False


def test_a_qualifying_filing_has_no_rejection_reason() -> None:
    assert rejection_reason(filing(), thesis()) is None


def test_an_amendment_is_rejected() -> None:
    reason = rejection_reason(filing(is_amendment=True), thesis())

    assert reason is not None
    assert "amendment" in reason


def test_amendments_pass_when_the_filter_is_off() -> None:
    lenient = thesis(
        filters={"min_offering_amount": 0, "exclude_amendments": False}
    )

    assert rejection_reason(filing(is_amendment=True), lenient) is None


def test_a_small_offering_is_rejected() -> None:
    # The $39 filing observed in real EDGAR data.
    reason = rejection_reason(filing(total_offering_amount=39), thesis())

    assert reason is not None
    assert "$39" in reason
    assert "$500,000" in reason


def test_an_undisclosed_amount_passes_by_default() -> None:
    # Form D permits indefinite offerings, and real healthcare companies file
    # that way — SleepRes, Angelis Oncology and Anavatos Bio all did in one
    # ten-day window. Dropping them would treat absence of evidence as evidence
    # of a nominal raise, and a missed company is the one failure a radar cannot
    # afford.
    assert rejection_reason(filing(total_offering_amount=None), thesis()) is None


def test_an_undisclosed_amount_can_be_rejected_when_asked_for() -> None:
    strict = thesis(
        filters={
            "min_offering_amount": 500_000,
            "require_disclosed_amount": True,
        }
    )

    reason = rejection_reason(filing(total_offering_amount=None), strict)

    assert reason == "no offering amount disclosed"


def test_the_floor_still_applies_to_a_disclosed_amount() -> None:
    lenient = thesis(filters={"min_offering_amount": 0})

    assert rejection_reason(filing(total_offering_amount=39), lenient) is None
    assert rejection_reason(filing(total_offering_amount=39), thesis()) is not None


def test_an_amount_exactly_on_the_floor_passes() -> None:
    assert rejection_reason(filing(total_offering_amount=500_000), thesis()) is None


def test_an_investment_vehicle_is_rejected_by_name() -> None:
    reason = rejection_reason(filing(company_name="Acme Fund II, LP"), thesis())

    assert reason is not None
    assert "investment vehicle" in reason


def test_apply_filters_splits_and_explains() -> None:
    kept, dropped = apply_filters(
        [
            filing(company_name="Acme Health, Inc."),
            filing(company_name="Tiny Co", total_offering_amount=39),
            filing(company_name="Acme Fund II, LP"),
            filing(company_name="Restated Inc.", is_amendment=True),
        ],
        thesis(),
    )

    assert [f.company_name for f in kept] == ["Acme Health, Inc."]
    assert len(dropped) == 3
    assert all(reason for _, reason in dropped)


def test_apply_filters_on_an_empty_list() -> None:
    assert apply_filters([], thesis()) == ([], [])


def test_prompt_description_includes_both_sides() -> None:
    rendered = describe_for_prompt(thesis())

    assert "Test thesis" in rendered
    assert "In scope:" in rendered
    assert "clinical software" in rendered
    assert "Out of scope:" in rendered
    assert "devices" in rendered


def test_prompt_description_omits_an_empty_exclude_list() -> None:
    rendered = describe_for_prompt(thesis(exclude=[]))

    assert "Out of scope:" not in rendered


def test_a_thesis_needs_at_least_one_include() -> None:
    with pytest.raises(Exception):
        Thesis.model_validate(
            {"domain": "D", "name": "x", "description": "y", "include": []}
        )
