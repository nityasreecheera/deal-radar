from contextlib import closing
from pathlib import Path

import pytest

from src.candidates import save_candidate
from src.models import Candidate, FormDFiling, RelatedPerson
from src.people import most_connected, name_key, save_people, shared_people
from src.seen import connect


def person(first: str, last: str, *roles: str, city: str = "Boston") -> RelatedPerson:
    return RelatedPerson(
        first_name=first,
        last_name=last,
        relationships=list(roles),
        city=city,
        state="MA",
    )


def candidate(name: str, accession: str, people: list[RelatedPerson]) -> Candidate:
    return Candidate(
        filing=FormDFiling(
            accession=accession,
            cik="1",
            company_name=name,
            filed_date="2026-07-30",
            industry_group="Other Technology",
            related_persons=people,
        ),
        verdict="fits",
        reason="Clinical software.",
    )


@pytest.fixture
def db(tmp_path: Path):
    with closing(connect(tmp_path / "radar.sqlite")) as connection:
        yield connection


def test_name_key_ignores_case_and_punctuation() -> None:
    assert name_key("Kenneth", "Gall") == name_key("KENNETH", "gall")
    assert name_key("Sean", "O'Brien") == name_key("sean", "obrien")


def test_name_key_of_an_empty_name_is_empty() -> None:
    assert name_key("", "") == ""
    assert name_key("  ", " ") == ""


def test_initials_are_not_treated_as_a_match() -> None:
    # Matching "R. Smith" to "Robert Smith" would invent a connection that is
    # not in the data.
    assert name_key("R.", "Smith") != name_key("Robert", "Smith")


def test_people_are_stored_when_a_candidate_is_saved(db) -> None:
    save_candidate(
        db,
        candidate("Huxley Medical, Inc.", "acc-1", [person("Kenneth", "Gall")]),
    )

    rows = db.execute("SELECT * FROM person").fetchall()

    assert len(rows) == 1
    assert rows[0]["full_name"] == "Kenneth Gall"


def test_a_person_on_one_company_is_not_a_connection(db) -> None:
    save_candidate(
        db,
        candidate("Huxley Medical, Inc.", "acc-1", [person("Kenneth", "Gall")]),
    )

    # Listing them would make the feature look busy while saying nothing.
    assert shared_people(db, "acc-1") == []


def test_a_person_on_two_companies_is_found(db) -> None:
    # The real one, from live data.
    save_candidate(
        db,
        candidate(
            "Huxley Medical, Inc.",
            "acc-1",
            [person("Kenneth", "Gall", "Director")],
        ),
    )
    save_candidate(
        db,
        candidate("Protect3d, Inc.", "acc-2", [person("Kenneth", "Gall", "Director")]),
    )

    links = shared_people(db, "acc-1")

    assert len(links) == 1
    assert links[0].full_name == "Kenneth Gall"
    assert links[0].other_companies == ["Protect3d, Inc."]
    assert links[0].relationships == ["Director"]


def test_the_link_works_from_either_company(db) -> None:
    save_candidate(db, candidate("A Inc", "acc-1", [person("Kenneth", "Gall")]))
    save_candidate(db, candidate("B Inc", "acc-2", [person("Kenneth", "Gall")]))

    assert shared_people(db, "acc-2")[0].other_companies == ["A Inc"]


def test_a_name_spelled_differently_still_links(db) -> None:
    save_candidate(db, candidate("A Inc", "acc-1", [person("Sean", "O'Brien")]))
    save_candidate(db, candidate("B Inc", "acc-2", [person("SEAN", "OBrien")]))

    assert len(shared_people(db, "acc-1")) == 1


def test_one_person_on_several_other_companies(db) -> None:
    for index, name in enumerate(["A Inc", "B Inc", "C Inc"], start=1):
        save_candidate(
            db, candidate(name, f"acc-{index}", [person("Kenneth", "Gall")])
        )

    links = shared_people(db, "acc-1")

    assert len(links) == 1
    assert sorted(links[0].other_companies) == ["B Inc", "C Inc"]


def test_several_people_shared_across_companies(db) -> None:
    # Two entities run by the same pair, which is what the real data showed for
    # the Imagen companies.
    pair = [person("Rezwan", "Manji"), person("David", "Diekmann")]

    save_candidate(db, candidate("Imagen Floss, LLC", "acc-1", pair))
    save_candidate(db, candidate("Imagen Glenview, LLC", "acc-2", pair))

    links = shared_people(db, "acc-1")

    assert {link.full_name for link in links} == {"Rezwan Manji", "David Diekmann"}


def test_unrelated_people_are_not_linked(db) -> None:
    save_candidate(db, candidate("A Inc", "acc-1", [person("Ada", "Lovelace")]))
    save_candidate(db, candidate("B Inc", "acc-2", [person("Alan", "Turing")]))

    assert shared_people(db, "acc-1") == []


def test_a_person_with_no_usable_name_is_skipped(db) -> None:
    assert save_people(db, "acc-1", [RelatedPerson()]) == 0


def test_most_connected_ranks_by_company_count(db) -> None:
    for index in range(1, 4):
        save_candidate(
            db,
            candidate(f"Co {index}", f"acc-{index}", [person("Kenneth", "Gall")]),
        )

    save_candidate(db, candidate("Co 4", "acc-4", [person("Ada", "Lovelace")]))
    save_candidate(db, candidate("Co 5", "acc-5", [person("Ada", "Lovelace")]))

    ranked = most_connected(db)

    assert ranked[0] == ("Kenneth Gall", 3)
    assert ("Ada Lovelace", 2) in ranked


def test_most_connected_excludes_people_on_one_company(db) -> None:
    save_candidate(db, candidate("Co 1", "acc-1", [person("Solo", "Founder")]))

    assert most_connected(db) == []
