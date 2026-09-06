import pytest

from src.profile import Unavailable, build_prompt, tidy, write_profile


SCRAPED = (
    "### The funders of the research projects include U.S. Department of Energy.  "
    "# Physical AI for data center cooling  Glacian helps data centers expand AI "
    "compute capacity.  Multi-Objective Optimization  Multi-Objective Optimization "
    "[...] The platform transforms complex technical data into clear metrics."
)


def test_tidy_removes_heading_markers() -> None:
    assert "#" not in tidy(SCRAPED)


def test_tidy_removes_the_truncation_marker() -> None:
    assert "[...]" not in tidy(SCRAPED)


def test_tidy_collapses_a_heading_the_layout_repeated() -> None:
    assert tidy(SCRAPED).count("Multi-Objective Optimization") == 1


def test_tidy_does_not_reword() -> None:
    """It is also the fallback when the model is unavailable, so it must not edit
    meaning — only remove artefacts of scraping."""
    assert "Glacian helps data centers expand AI compute capacity" in tidy(SCRAPED)


def test_tidy_handles_nothing() -> None:
    assert tidy(None) == ""
    assert tidy("") == ""


def test_the_prompt_carries_only_what_was_found() -> None:
    prompt = build_prompt("Glacian Technologies Inc.", None, SCRAPED, None, None, 150_000)

    assert "Glacian Technologies Inc." in prompt
    assert "$150,000" in prompt
    assert "not found" in prompt          # no website on record, said so
    assert "[...]" not in prompt          # the model sees the tidied text


def test_a_profile_is_written_from_the_material() -> None:
    def fake_chat(system: str, prompt: str) -> str:
        assert "Glacian" in prompt
        return "They sell software for data centre cooling."

    assert write_profile("Glacian", description=SCRAPED, chat=fake_chat).startswith(
        "They sell"
    )


def test_nothing_to_explain_is_not_explained() -> None:
    """With no material, a profile could only be invented."""
    with pytest.raises(Unavailable):
        write_profile("Mystery Corp", chat=lambda system, prompt: "It is a company.")


def test_an_unreachable_model_writes_nothing(caplog) -> None:
    """
    Not a fabricated profile, and not an empty one presented as the answer. The
    caller falls back to the company's own words instead.
    """
    def broken(system: str, prompt: str) -> str:
        raise RuntimeError("402 Payment Required")

    with pytest.raises(Unavailable, match="402"):
        write_profile("Glacian", description=SCRAPED, chat=broken)


def test_an_empty_reply_is_not_a_profile() -> None:
    with pytest.raises(Unavailable):
        write_profile("Glacian", description=SCRAPED, chat=lambda s, p: "   ")
