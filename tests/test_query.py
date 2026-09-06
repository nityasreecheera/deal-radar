from src.query import parse_query


THEMES = ["Healthcare", "AI tools", "AI infra", "Energy", "Fintech"]


def test_plain_words_stay_a_text_search() -> None:
    parsed = parse_query("cooling")

    assert parsed.text == "cooling"
    assert not parsed.is_structured


def test_a_stage_becomes_a_cheque_size() -> None:
    parsed = parse_query("pre-seed companies")

    assert parsed.max_amount == 3_000_000
    assert parsed.text == ""
    assert parsed.reading == ["pre-seed — under $3M"]


def test_an_explicit_size_beats_the_stage_convention() -> None:
    """'seed under $2M' means two million, not the seed ceiling."""
    parsed = parse_query("seed under $2m")

    assert parsed.max_amount == 2_000_000


def test_sizes_in_thousands_and_millions() -> None:
    assert parse_query("under $500k").max_amount == 500_000
    assert parse_query("over 1.5m").min_amount == 1_500_000
    assert parse_query("under 750000").max_amount == 750_000


def test_a_domain_is_recognised() -> None:
    parsed = parse_query("AI infra companies", THEMES)

    assert parsed.theme == "AI infra"
    assert parsed.text == ""


def test_the_longest_matching_domain_wins() -> None:
    """A theme whose name contains another's must not be shadowed by it."""
    parsed = parse_query("AI infra", ["AI", "AI infra"])

    assert parsed.theme == "AI infra"


def test_verdict_words() -> None:
    assert parse_query("fits").verdicts == ["fits"]
    assert parse_query("rejected").verdicts == ["no_fit"]
    assert set(parse_query("fits and maybes").verdicts) == {"fits", "maybe"}


def test_a_whole_sentence() -> None:
    parsed = parse_query(
        "show me pre-seed AI infra companies under $1m that fit, about cooling",
        THEMES,
    )

    assert parsed.theme == "AI infra"
    assert parsed.max_amount == 1_000_000
    assert parsed.verdicts == ["fits"]
    assert parsed.text == "cooling"


def test_recognised_phrases_do_not_also_become_search_words() -> None:
    """
    'pre-seed' must not survive into the text search: no company description
    contains the phrase, so it would match nothing and empty the results.
    """
    parsed = parse_query("pre-seed cooling", THEMES)

    assert parsed.text == "cooling"


def test_what_it_cannot_answer_is_reported_not_ignored() -> None:
    """
    Silently dropping 'technical founders' would return a confident list that
    does not honour the question, which is the failure this project keeps
    finding. It says so instead.
    """
    parsed = parse_query("pre-seed companies with technical founders")

    assert parsed.unsupported
    assert "technical" in parsed.unsupported[0]
    assert parsed.max_amount == 3_000_000


def test_dates() -> None:
    assert parse_query("filed this year").since.endswith("-01-01")
    assert parse_query("in the last 3 months").since is not None
    assert parse_query("since 2026").since == "2026-01-01"


def test_an_empty_question_parses_to_nothing() -> None:
    parsed = parse_query("   ")

    assert parsed.text == ""
    assert not parsed.is_structured
    assert parsed.verdicts == []


# --- how the parser is used to choose what the model sees ------------------

from contextlib import closing
from pathlib import Path

import pytest

from src.candidates import save_candidate
from src.chat import answer_question
from src.seen import connect
from tests.test_candidates import candidate


@pytest.fixture
def db(tmp_path: Path):
    with closing(connect(tmp_path / "radar.sqlite")) as connection:
        yield connection


def seen_by_model(db, question: str, **kwargs) -> list[str]:
    """Ask, and report which companies were put in front of the model."""
    captured: list[str] = []

    def fake_chat(system: str, prompt: str) -> str:
        captured.append(prompt)
        return "an answer"

    answer_question(db, question, chat=fake_chat, **kwargs)

    return [name for name in ("Glacian", "Genomenon", "DriveNets") if name in captured[0]]


def test_the_question_chooses_the_rows_not_recency(db) -> None:
    """
    A size in the question must narrow the sample. Answering from the newest
    rows regardless is how a confident answer gets drawn from the wrong set.
    """
    save_candidate(db, candidate(name="Glacian", accession="a", amount=150_000,
                                 filed_date="2026-01-01"))
    save_candidate(db, candidate(name="DriveNets", accession="b", amount=410_000_000,
                                 filed_date="2026-08-03"))

    assert seen_by_model(db, "pre-seed companies") == ["Glacian"]


def test_leftover_words_do_not_empty_the_sample(db) -> None:
    """
    'Why did we pass on those?' leaves words no filing contains. Letting them
    filter would hand the model nothing and produce 'no record' for a question
    the database can answer.
    """
    save_candidate(db, candidate(name="Genomenon", accession="a", verdict="no_fit"))

    assert seen_by_model(db, "why did we pass on those?") == ["Genomenon"]


def test_a_domain_in_the_question_selects_that_domain(db) -> None:
    save_candidate(db, candidate(name="Glacian", accession="a"), theme="AI infra")
    save_candidate(db, candidate(name="Genomenon", accession="b"), theme="Healthcare")

    seen = seen_by_model(db, "AI infra companies", themes=["AI infra", "Healthcare"])

    assert seen == ["Glacian"]


def test_the_search_term_is_named_alongside_other_filters(db) -> None:
    parsed = parse_query("pre-seed cooling")

    assert "matching “cooling”" in parsed.reading


def test_a_bare_word_does_not_restate_itself(db) -> None:
    """For plain words the reading would just repeat the box."""
    assert parse_query("cooling").reading == []
