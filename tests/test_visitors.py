"""
A visitor's own domains: theirs alone, judged cheaply, never in the owner's record.

What has to be proved is mostly about who sees what. A visitor's domain appears
in their dropdown and their list; it does not appear for another visitor; and
nothing about it reaches the owner — not the domain, not a verdict, not a row in
the owner's table.
"""

import json
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.api as api_module
import src.seen as seen_module
import src.visibility as visibility_module
import src.visitors as visitors_module
from src.api import app
from src.candidates import save_candidate
from src.models import Candidate, FormDFiling
from src.seen import connect
from src.thesis import Thesis


client = TestClient(app)

ALICE = {"x-radar-viewer": "public", "x-radar-visitor-id": "11111111-1111-4111-8111-111111111111"}
BOB = {"x-radar-viewer": "public", "x-radar-visitor-id": "22222222-2222-4222-8222-222222222222"}
OWNER = {"x-radar-viewer": "owner"}


def thesis(domain: str, public: bool = True) -> Thesis:
    return Thesis.model_validate(
        {"domain": domain, "name": domain, "description": "x", "include": ["x"], "public": public}
    )


def company(name: str, accession: str, description: str, amount: int = 5_000_000) -> Candidate:
    return Candidate(
        filing=FormDFiling(
            accession=accession,
            cik="1",
            company_name=name,
            filed_date="2026-09-01",
            industry_group="Other Technology",
            total_offering_amount=amount,
        ),
        verdict="no_fit",
        reason="Owner's thesis reason.",
        description=description,
    )


judged_names: list[str] = []


def fake_judge(system: str, user: str) -> str:
    """Fits anything that mentions robots, rejects the rest. Records what it saw."""
    judged_names.append(user)
    verdict = "fits" if "robot" in user.lower() else "no_fit"

    return json.dumps({"verdict": verdict, "reason": "Visitor's thesis reason.", "summary": "A company."})


@pytest.fixture(autouse=True)
def site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(seen_module, "DEFAULT_DB_PATH", tmp_path / "radar.sqlite")
    monkeypatch.setattr(api_module, "DIGEST_DIR", tmp_path / "digests")

    theses = [thesis("Healthcare"), thesis("Parallax", public=False)]
    monkeypatch.setattr(visibility_module, "load_all_theses", lambda: theses)
    monkeypatch.setattr(api_module, "available_themes", lambda: ["Healthcare", "Parallax"])
    monkeypatch.setattr(visitors_module, "create_openai_compatible_judge", lambda model=None: fake_judge)
    monkeypatch.setattr(visitors_module, "BATCH", 2)
    judged_names.clear()

    with closing(connect()) as connection:
        save_candidate(connection, company("RoboArm Inc", "acc-1", "Industrial robot arms for factories."), theme="Healthcare")
        save_candidate(connection, company("CareNote", "acc-2", "Clinical notes software."), theme="Healthcare")
        save_candidate(connection, company("Robo Kitchen", "acc-3", "Robots that cook in restaurants."), theme="Healthcare")
        save_candidate(connection, company("Tiny Bot", "acc-4", "Robot toys.", amount=10_000), theme="Healthcare")
        # Known only to a private domain: never offered to a visitor.
        save_candidate(connection, company("Secret Robots", "acc-5", "Robots in secret."), theme="Parallax")


def add(headers: dict, **overrides) -> dict:
    body = {"domain": "Robotics", "include": ["robots and automation"], **overrides}
    response = client.post("/api/visitor/domains", json=body, headers=headers)
    assert response.status_code == 200, response.text

    return response.json()


# --- a visitor's own domain ---------------------------------------------------

def test_adding_a_domain_judges_a_first_batch() -> None:
    result = add(ALICE)

    assert result["theme"] == "Robotics (yours)"
    assert result["judged"] == 2
    assert result["fits"] == 2


def test_the_best_matches_are_judged_first() -> None:
    add(ALICE)

    assert all("robot" in prompt.lower() for prompt in judged_names)


def test_the_domain_appears_in_the_visitors_dropdown_and_list() -> None:
    add(ALICE)

    meta = client.get("/api/meta", headers=ALICE).json()
    rows = client.get("/api/candidates", params={"theme": "Robotics (yours)"}, headers=ALICE).json()["candidates"]

    assert "Robotics (yours)" in meta["themes"]
    assert {row["company_name"] for row in rows} == {"RoboArm Inc", "Robo Kitchen"}
    assert all(row["reason"] == "Visitor's thesis reason." for row in rows)


def test_the_visitors_company_page_shows_their_verdict() -> None:
    add(ALICE)

    found = client.get("/api/candidates/acc-1", params={"theme": "Robotics (yours)"}, headers=ALICE).json()

    assert found["verdict"] == "fits"
    assert found["reason"] == "Visitor's thesis reason."


def test_the_visitors_min_raise_is_applied_before_judging() -> None:
    add(ALICE, min_amount=1_000_000)

    assert not any("Tiny Bot" in prompt for prompt in judged_names)


def test_judging_more_continues_where_the_last_batch_stopped() -> None:
    add(ALICE)
    more = client.post("/api/visitor/domains/Robotics (yours)/more", headers=ALICE).json()

    # Tiny Bot and CareNote: the two the first batch of two did not reach.
    assert more["judged"] == 2
    assert more["left"] == 0


def test_a_company_only_a_private_domain_found_is_never_offered() -> None:
    add(ALICE)
    client.post("/api/visitor/domains/Robotics (yours)/more", headers=ALICE)

    assert not any("Secret Robots" in prompt for prompt in judged_names)


# --- theirs alone -------------------------------------------------------------

def test_another_visitor_does_not_see_it() -> None:
    add(ALICE)

    meta = client.get("/api/meta", headers=BOB).json()
    rows = client.get("/api/candidates", params={"theme": "Robotics (yours)"}, headers=BOB).json()["candidates"]

    assert "Robotics (yours)" not in meta["themes"]
    assert rows == []
    assert client.get("/api/visitor/domains", headers=BOB).json() == []


def test_the_owner_never_sees_it() -> None:
    add(ALICE)

    meta = client.get("/api/meta", headers=OWNER).json()
    rows = client.get("/api/candidates", params={"limit": 500}, headers=OWNER).json()["candidates"]

    assert "Robotics (yours)" not in meta["themes"]
    assert all(row["theme"] != "Robotics (yours)" for row in rows)
    assert {row["reason"] for row in rows} == {"Owner's thesis reason."}


def test_nothing_is_written_to_the_owners_table() -> None:
    with closing(connect()) as connection:
        before = connection.execute("SELECT COUNT(*) FROM candidate").fetchone()[0]

    add(ALICE)

    with closing(connect()) as connection:
        after = connection.execute("SELECT COUNT(*) FROM candidate").fetchone()[0]

    assert after == before


def test_a_name_like_a_real_domain_does_not_mix_with_it() -> None:
    add(ALICE, domain="Healthcare")

    real = client.get("/api/candidates", params={"theme": "Healthcare"}, headers=ALICE).json()["candidates"]

    assert {row["reason"] for row in real} == {"Owner's thesis reason."}


def test_deleting_removes_it_and_its_results() -> None:
    add(ALICE)
    assert client.delete("/api/visitor/domains/Robotics (yours)", headers=ALICE).status_code == 200

    meta = client.get("/api/meta", headers=ALICE).json()

    assert "Robotics (yours)" not in meta["themes"]
    assert client.get("/api/visitor/domains", headers=ALICE).json() == []


def test_a_visitor_cannot_delete_someone_elses_domain() -> None:
    add(ALICE)

    assert client.delete("/api/visitor/domains/Robotics (yours)", headers=BOB).status_code == 404


# --- limits ---------------------------------------------------------------------

def test_the_hourly_limit_stops_a_visitor(monkeypatch) -> None:
    monkeypatch.setattr(visitors_module, "TRIES_PER_HOUR", 1)
    add(ALICE)

    response = client.post("/api/visitor/domains/Robotics (yours)/more", headers=ALICE)

    assert response.status_code == 429
    assert "this hour" in response.json()["detail"]["errors"][0]


def test_the_site_wide_daily_limit_stops_everyone(monkeypatch) -> None:
    monkeypatch.setattr(visitors_module, "TRIES_PER_DAY", 1)
    add(ALICE)

    response = client.post("/api/visitor/domains", json={"domain": "Other", "include": ["x"]}, headers=BOB)

    assert response.status_code == 429


def test_the_number_of_domains_is_capped(monkeypatch) -> None:
    monkeypatch.setattr(visitors_module, "MAX_DOMAINS", 1)
    add(ALICE)

    response = client.post("/api/visitor/domains", json={"domain": "Second", "include": ["x"]}, headers=ALICE)

    assert response.status_code == 422


def test_the_same_name_twice_is_refused() -> None:
    add(ALICE)

    response = client.post("/api/visitor/domains", json={"domain": "Robotics", "include": ["x"]}, headers=ALICE)

    assert response.status_code == 422


def test_the_owner_cannot_use_visitor_domains() -> None:
    response = client.post("/api/visitor/domains", json={"domain": "X", "include": ["x"]}, headers=OWNER)

    assert response.status_code == 403


def test_a_malformed_visitor_id_is_ignored() -> None:
    headers = {"x-radar-viewer": "public", "x-radar-visitor-id": "not-an-id"}

    assert client.post("/api/visitor/domains", json={"domain": "X", "include": ["x"]}, headers=headers).status_code == 403


# --- matching ---------------------------------------------------------------------

def test_two_letter_words_count_and_plurals_match() -> None:
    from src.visitors import words

    assert {"ai", "battery", "centre"} <= words("AI for batteries in data centres")


def test_words_match_whole_words_not_fragments() -> None:
    from src.visitors import words

    assert "car" not in words("healthcare cardiology")
