"""
Editing criteria from the browser.

The site can now rewrite the files the daily run reads. Everything here guards
that seam: a malformed edit must not reach disk, a domain name must not escape
the config directory, and deleting criteria must not delete history.
"""

from pathlib import Path

import pytest

from src.thesis import (
    Thesis,
    ThesisError,
    delete_thesis,
    find_thesis_path,
    load_all_theses,
    load_thesis,
    save_thesis,
    thesis_filename,
)


def a_thesis(domain: str = "Robotics", **overrides) -> Thesis:
    data = {
        "domain": domain,
        "name": f"{domain} companies",
        "description": "Something worth reading.",
        "include": ["one thing"],
        "exclude": ["another thing"],
        "sec_industry_groups": ["Other Technology"],
    }
    data.update(overrides)

    return Thesis(**data)


def test_saving_then_loading_returns_the_same_criteria(tmp_path: Path) -> None:
    save_thesis(a_thesis(), directory=tmp_path)

    loaded = load_thesis(next(tmp_path.glob("*.yaml")))

    assert loaded.domain == "Robotics"
    assert loaded.include == ["one thing"]


def test_a_domain_name_cannot_escape_the_config_directory(tmp_path: Path) -> None:
    # The name becomes a filename. Anything with a slash or a dot in it is
    # either a mistake or an attempt to write somewhere else.
    for bad in ("../etc/passwd", "a/b", "..", "with.dot"):
        with pytest.raises((ThesisError, ValueError)):
            save_thesis(a_thesis(domain=bad), directory=tmp_path)

    assert list(tmp_path.glob("*.yaml")) == []


def test_an_empty_include_list_is_refused() -> None:
    # A thesis that includes nothing matches nothing, which is a silent way to
    # switch a domain off while it looks configured.
    with pytest.raises(Exception):
        a_thesis(include=[])


def test_editing_writes_back_to_the_file_it_came_from(tmp_path: Path) -> None:
    first = save_thesis(a_thesis(), directory=tmp_path)

    save_thesis(
        a_thesis(include=["something else"]),
        directory=tmp_path,
        original_domain="Robotics",
    )

    # One file, updated — not a second one alongside it.
    assert list(tmp_path.glob("*.yaml")) == [first]
    assert load_thesis(first).include == ["something else"]


def test_renaming_a_domain_keeps_one_file(tmp_path: Path) -> None:
    save_thesis(a_thesis(domain="Robots"), directory=tmp_path)

    save_thesis(
        a_thesis(domain="Robotics"),
        directory=tmp_path,
        original_domain="Robots",
    )

    files = list(tmp_path.glob("*.yaml"))

    assert len(files) == 1
    assert load_thesis(files[0]).domain == "Robotics"


def test_two_domains_cannot_share_a_name(tmp_path: Path) -> None:
    save_thesis(a_thesis(domain="Robotics"), directory=tmp_path)

    with pytest.raises(ThesisError, match="already exists"):
        save_thesis(a_thesis(domain="Robotics"), directory=tmp_path)


def test_deleting_removes_the_file(tmp_path: Path) -> None:
    save_thesis(a_thesis(), directory=tmp_path)

    assert delete_thesis("Robotics", directory=tmp_path) is True
    assert list(tmp_path.glob("*.yaml")) == []

    # Deleting something that is not there is not an error, just nothing done.
    assert delete_thesis("Robotics", directory=tmp_path) is False


def test_a_half_written_file_is_never_visible(tmp_path: Path) -> None:
    save_thesis(a_thesis(), directory=tmp_path)

    # Written to a temporary name and renamed, so a run reading the directory
    # mid-save sees the old file or the new one, never half of either.
    assert list(tmp_path.glob("*.tmp")) == []


def test_an_unreadable_file_does_not_hide_the_others(tmp_path: Path) -> None:
    save_thesis(a_thesis(domain="Robotics"), directory=tmp_path)
    (tmp_path / "broken.yaml").write_text("{{{ not yaml", encoding="utf-8")

    assert [t.domain for t in load_all_theses(tmp_path)] == ["Robotics"]


def test_filenames_are_derived_from_the_domain() -> None:
    assert thesis_filename("AI infra") == "ai-infra.yaml"
    assert thesis_filename("Energy") == "energy.yaml"
    assert thesis_filename("  Odd   Name  ") == "odd-name.yaml"


def test_the_original_healthcare_file_keeps_its_name(tmp_path: Path) -> None:
    # It lives in thesis.yaml, and every command anyone has written down points
    # at that path. Editing it must not quietly rename it to healthcare.yaml.
    (tmp_path / "thesis.yaml").write_text(
        "domain: Healthcare\nname: Health\ndescription: d\ninclude: [x]\n",
        encoding="utf-8",
    )

    save_thesis(
        a_thesis(domain="Healthcare"),
        directory=tmp_path,
        original_domain="Healthcare",
    )

    assert find_thesis_path("Healthcare", tmp_path).name == "thesis.yaml"
