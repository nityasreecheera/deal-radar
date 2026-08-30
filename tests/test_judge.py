import pytest

from src.enrich import Enrichment
from src.judge import (
    SYSTEM_PROMPT,
    JudgementError,
    build_prompt,
    judge_filing,
    parse_judgement,
)
from src.models import FormDFiling, RelatedPerson
from src.thesis import Thesis


def filing(**overrides) -> FormDFiling:
    data = {
        "accession": "acc-1",
        "cik": "1",
        "company_name": "Acme Health, Inc.",
        "filed_date": "2026-07-27",
        "industry_group": "Other Health Care",
        "city": "BOSTON",
        "state": "MA",
        "year_of_incorporation": 2025,
        "entity_type": "Corporation",
        "total_offering_amount": 4_000_000,
        "related_persons": [
            RelatedPerson(
                first_name="Ada",
                last_name="Lovelace",
                relationships=["Executive Officer", "Director"],
            )
        ],
    }
    data.update(overrides)

    return FormDFiling(**data)


def thesis() -> Thesis:
    return Thesis.model_validate(
        {
            "domain": "Healthcare",
            "name": "Healthcare software",
            "description": "Software for clinical workflows.",
            "include": ["clinical trial software"],
            "exclude": ["medical devices"],
        }
    )


def test_prompt_states_when_evidence_came_from_the_company_itself() -> None:
    prompt = build_prompt(
        filing(),
        Enrichment(
            website="https://acmehealth.com",
            description="We match patients to trials.",
            confident=True,
        ),
        thesis(),
    )

    assert "From the company's own site" in prompt
    assert "acmehealth.com" in prompt
    assert "weak evidence" not in prompt


def test_prompt_flags_third_party_evidence_as_weak() -> None:
    prompt = build_prompt(
        filing(),
        Enrichment(description="Listed in a healthcare directory.", confident=False),
        thesis(),
    )

    assert "weak evidence" in prompt
    assert "No company website could be identified" in prompt


def test_prompt_says_plainly_when_nothing_was_found() -> None:
    prompt = build_prompt(filing(), Enrichment(), thesis())

    assert "Nothing could be found" in prompt


def test_prompt_includes_the_filing_facts() -> None:
    prompt = build_prompt(filing(), Enrichment(), thesis())

    assert "Acme Health, Inc." in prompt
    assert "Other Health Care" in prompt
    assert "BOSTON" in prompt
    assert "$4,000,000" in prompt
    assert "Ada Lovelace" in prompt
    assert "Healthcare software" in prompt


def test_prompt_handles_an_undisclosed_amount() -> None:
    prompt = build_prompt(
        filing(total_offering_amount=None), Enrichment(), thesis()
    )

    assert "undisclosed" in prompt


def test_prompt_handles_a_filing_with_no_people() -> None:
    prompt = build_prompt(filing(related_persons=[]), Enrichment(), thesis())

    assert "none listed" in prompt


def test_parse_a_clean_answer() -> None:
    judgement = parse_judgement('{"verdict": "fits", "reason": "Trial software."}')

    assert judgement.verdict == "fits"
    assert judgement.is_interesting is True


def test_parse_an_answer_wrapped_in_prose() -> None:
    raw = 'Here is my answer:\n```json\n{"verdict": "no_fit", "reason": "A clinic."}\n```'

    judgement = parse_judgement(raw)

    assert judgement.verdict == "no_fit"
    assert judgement.is_interesting is False


def test_maybe_counts_as_interesting() -> None:
    judgement = parse_judgement('{"verdict": "maybe", "reason": "Too little info."}')

    assert judgement.is_interesting is True


def test_parse_rejects_an_answer_with_no_json() -> None:
    with pytest.raises(JudgementError, match="no JSON object"):
        parse_judgement("I think it probably fits, hard to say.")


def test_parse_rejects_malformed_json() -> None:
    with pytest.raises(JudgementError, match="not valid JSON"):
        parse_judgement('{"verdict": "fits", "reason": }')


def test_parse_rejects_an_unknown_verdict() -> None:
    # Defaulting here would put an unexamined company in front of an analyst.
    with pytest.raises(JudgementError, match="did not match the schema"):
        parse_judgement('{"verdict": "looks good", "reason": "Seems fine."}')


def test_parse_rejects_a_missing_reason() -> None:
    with pytest.raises(JudgementError, match="did not match the schema"):
        parse_judgement('{"verdict": "fits"}')


def test_parse_rejects_an_empty_reason() -> None:
    with pytest.raises(JudgementError, match="did not match the schema"):
        parse_judgement('{"verdict": "fits", "reason": ""}')


def test_judge_filing_returns_a_candidate() -> None:
    def fake_judge(system: str, user: str) -> str:
        assert "screen companies" in system
        assert "Acme Health" in user

        return '{"verdict": "fits", "reason": "Clinical trial matching software."}'

    candidate = judge_filing(
        filing(),
        Enrichment(
            website="https://acmehealth.com",
            description="Trial matching.",
            confident=True,
        ),
        thesis(),
        judge=fake_judge,
    )

    assert candidate.verdict == "fits"
    assert candidate.reason == "Clinical trial matching software."
    assert candidate.website == "https://acmehealth.com"
    assert candidate.filing.company_name == "Acme Health, Inc."


def test_judge_filing_propagates_a_bad_answer() -> None:
    def fake_judge(system: str, user: str) -> str:
        return "no idea"

    with pytest.raises(JudgementError):
        judge_filing(filing(), Enrichment(), thesis(), judge=fake_judge)


def test_unknown_is_a_verdict_and_is_not_interesting() -> None:
    # "unknown" means nobody established what the company does. That is a
    # research task, not a judgement to read over coffee, so it stays out of the
    # digest even though it is not a rejection.
    judgement = parse_judgement(
        '{"verdict": "unknown", "reason": "Placeholder site only.",'
        ' "summary": null}'
    )

    assert judgement.verdict == "unknown"
    assert judgement.is_interesting is False
    assert judgement.summary is None


def test_the_prompt_distinguishes_maybe_from_unknown() -> None:
    # Collapsing them is what filled twelve of twenty maybes with shrugs.
    assert "maybe" in SYSTEM_PROMPT
    assert "unknown" in SYSTEM_PROMPT
    assert "a maybe is worth" in SYSTEM_PROMPT


def test_the_prompt_asks_for_a_summary_separate_from_the_reason() -> None:
    assert "summary describes the business" in SYSTEM_PROMPT
    assert "Do not merge them" in SYSTEM_PROMPT


def test_a_summary_is_carried_onto_the_candidate() -> None:
    def fake_judge(system: str, user: str) -> str:
        return (
            '{"verdict": "fits", "reason": "Clinical trial software.",'
            ' "summary": "Matches patients to oncology trials."}'
        )

    candidate = judge_filing(
        filing(), Enrichment(), thesis(), judge=fake_judge
    )

    assert candidate.summary == "Matches patients to oncology trials."
    # The reason explains the verdict; the summary describes the business.
    assert candidate.reason != candidate.summary


def test_a_missing_summary_is_allowed() -> None:
    judgement = parse_judgement(
        '{"verdict": "unknown", "reason": "No evidence at all."}'
    )

    assert judgement.summary is None


def test_the_configured_key_wins_over_a_leftover_one(monkeypatch) -> None:
    """
    Switching provider without clearing the old key is the obvious mistake, and
    it fails as a 401 that reads like a bad key rather than the wrong one.
    """
    from src.judge import llm_api_key

    monkeypatch.setenv("LLM_API_KEY", "the-one-i-meant")
    monkeypatch.setenv("OPENROUTER_API_KEY", "an-old-one-still-in-dotenv")

    assert llm_api_key() == "the-one-i-meant"


def test_a_provider_specific_key_still_works_alone(monkeypatch) -> None:
    from src.judge import llm_api_key

    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-whatever")

    assert llm_api_key() == "sk-whatever"


def test_no_key_anywhere_is_none(monkeypatch) -> None:
    from src.judge import llm_api_key

    for name in (
        "LLM_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENROUTER_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    assert llm_api_key() is None
