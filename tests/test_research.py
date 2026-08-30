"""
Founders' research records, and refusing the wrong one.

Every case here is real. Searching "Alonso Galvan" returns a Spanish hospital
oncologist and Cornelis Networks makes networking hardware in Pennsylvania —
a confident wrong attribution about a named person is worse than saying nothing.
"""

from src.research import (
    MIN_WORKS,
    Researcher,
    candidates_for,
    check_plausible,
    parse_author,
)


def author(name: str, works: int, citations: int = 0, topics=None, institution=""):
    return {
        "id": f"https://openalex.org/{name.replace(' ', '')}",
        "display_name": name,
        "works_count": works,
        "cited_by_count": citations,
        "last_known_institutions": (
            [{"display_name": institution}] if institution else []
        ),
        "topics": [{"display_name": t} for t in (topics or [])],
    }


def test_a_record_is_parsed_whole() -> None:
    parsed = parse_author(
        author(
            "Koroush Shirvan",
            247,
            3037,
            ["Nuclear reactor physics and engineering"],
            "MIT",
        )
    )

    assert parsed.works == 247
    assert parsed.citations == 3037
    assert parsed.institution == "MIT"
    assert "nuclear" in parsed.summary


def test_a_thin_record_is_not_even_considered() -> None:
    # Real: "Alonso Galvan", 4 works, an oncologist. Every false match in
    # testing had fewer than five papers; the true one had 247.
    thin = candidates_for("Alonso Galvan", lookup=lambda n: [author("Alonso Galvan", 4)])

    assert thin == []


def test_a_substantial_record_survives_the_threshold() -> None:
    found = candidates_for(
        "Koroush Shirvan", lookup=lambda n: [author("Koroush Shirvan", 247, 3037)]
    )

    assert len(found) == 1
    assert found[0].works >= MIN_WORKS


def test_an_empty_name_is_not_searched() -> None:
    def never(name: str):  # pragma: no cover - must not be called
        raise AssertionError("should not search for an empty name")

    assert candidates_for("", lookup=never) == []
    assert candidates_for("   ", lookup=never) == []


def test_an_unreachable_service_is_not_a_crash() -> None:
    def broken(name: str):
        raise RuntimeError("openalex is down")

    assert candidates_for("Anyone", lookup=broken) == []


def test_a_matching_field_is_accepted() -> None:
    shirvan = Researcher(
        name="Koroush Shirvan",
        works=247,
        topics=["Nuclear reactor physics and engineering"],
    )

    assert check_plausible(
        shirvan,
        "OrganiCore Nuclear, Inc.",
        "Nuclear reactor technology",
        judge=lambda system, prompt: '{"plausible": true}',
    )


def test_an_unrelated_field_is_refused() -> None:
    galvan = Researcher(
        name="Alonso Galvan",
        works=40,
        topics=["Pancreatic and Hepatic Oncology Research"],
    )

    assert not check_plausible(
        galvan,
        "Cornelis Networks, Inc.",
        "Networking hardware for AI training clusters",
        judge=lambda system, prompt: '{"plausible": false}',
    )


def test_an_unreadable_answer_means_no() -> None:
    # Silence is not a yes. A wrong attribution about a real person is the
    # failure that matters here.
    someone = Researcher(name="Someone", works=50)

    assert not check_plausible(
        someone, "Acme", "Anything", judge=lambda s, p: "I'm not sure, possibly?"
    )


def test_an_unreachable_model_is_not_a_rejection() -> None:
    """
    An account out of credit produced "checked 40, plausible matches 0" — a
    finding nobody made, indistinguishable from having genuinely checked. The
    same mistake as an EDGAR outage reading as a quiet morning.
    """
    import pytest

    from src.research import Unavailable

    def broken(system: str, prompt: str) -> str:
        raise RuntimeError("402 Payment Required")

    with pytest.raises(Unavailable):
        check_plausible(
            Researcher(name="Someone", works=50), "Acme", "Anything", judge=broken
        )


def test_the_prompt_carries_what_the_company_does() -> None:
    seen = {}

    def judge(system: str, prompt: str) -> str:
        seen["prompt"] = prompt
        return '{"plausible": false}'

    check_plausible(
        Researcher(name="X", works=20, topics=["Marine Biology"]),
        "Cornelis Networks, Inc.",
        "Networking hardware",
        judge=judge,
    )

    # Without the company's business the model is guessing from the name alone,
    # which is the thing this exists to avoid.
    assert "Networking hardware" in seen["prompt"]
    assert "Marine Biology" in seen["prompt"]
