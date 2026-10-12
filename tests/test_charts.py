"""
Charts from plain-English questions.

The model is replaced by a fake that returns a fixed plan, because what matters
is everything after it: that the numbers come from the data and not the model,
that a visitor's chart is drawn only from what a visitor may read, and that a
plan outside the closed set of choices is refused rather than half-followed.
"""

import json
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.api as api_module
import src.charts as charts_module
import src.seen as seen_module
import src.visibility as visibility_module
from src.api import app
from src.candidates import record_decision, save_candidate
from src.models import Candidate, FormDFiling
from src.seen import connect
from src.thesis import Thesis


client = TestClient(app)

OWNER = {"x-radar-viewer": "owner"}
VISITOR = {"x-radar-viewer": "public", "x-radar-visitor-id": "33333333-3333-4333-8333-333333333333"}


def thesis(domain: str, public: bool = True) -> Thesis:
    return Thesis.model_validate(
        {"domain": domain, "name": domain, "description": "x", "include": ["x"], "public": public}
    )


def company(name, accession, verdict, amount, sold=None, filed="2026-09-01", state="CA"):
    return Candidate(
        filing=FormDFiling(
            accession=accession,
            cik="1",
            company_name=name,
            filed_date=filed,
            industry_group="Other Technology",
            state=state,
            total_offering_amount=amount,
            total_amount_sold=sold,
        ),
        verdict=verdict,
        reason="Because.",
    )


plans: list[dict] = []


def planner(system: str, user: str) -> str:
    return json.dumps(plans.pop(0))


@pytest.fixture(autouse=True)
def site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(seen_module, "DEFAULT_DB_PATH", tmp_path / "radar.sqlite")
    monkeypatch.setattr(api_module, "DIGEST_DIR", tmp_path / "digests")
    theses = [thesis("AI infra"), thesis("Parallax", public=False)]
    monkeypatch.setattr(visibility_module, "load_all_theses", lambda: theses)
    monkeypatch.setattr(api_module, "available_themes", lambda: ["AI infra", "Parallax"])
    monkeypatch.setattr(api_module, "chart_planner", lambda: planner)
    plans.clear()

    with closing(connect()) as connection:
        save_candidate(connection, company("Tenstorrent Holdings", "acc-t", "fits", 1_416_000_000, 900_000_000), theme="AI infra")
        save_candidate(connection, company("Fab2, Inc.", "acc-f", "fits", 588_000_000, 100_000_000, filed="2026-08-15"), theme="AI infra")
        save_candidate(connection, company("Small Co", "acc-s", "no_fit", 2_000_000, filed="2026-08-20", state="NY"), theme="AI infra")
        save_candidate(connection, company("Hidden Co", "acc-h", "fits", 50_000_000), theme="Parallax")
        record_decision(connection, "acc-s", verdict="fits", note="Owner thinks otherwise.")


def ask(question: str, plan: dict, headers=OWNER):
    plans.append(plan)

    return client.post("/api/charts", json={"question": question}, headers=headers)


# --- the three kinds of chart ---------------------------------------------------

def test_compare_puts_two_companies_side_by_side() -> None:
    body = ask("Tenstorrent vs Fab2", {"kind": "compare", "companies": ["Tenstorrent", "fab2"]}).json()

    assert body["form"] == "grouped"
    assert [s["name"] for s in body["series"]] == ["Tenstorrent Holdings", "Fab2, Inc."]
    assert body["series"][0]["values"] == [1_416_000_000, 900_000_000]
    assert body["rows"][0] == ["Being raised", "$1.4B", "$588.0M"]


def test_compare_says_which_company_it_could_not_find() -> None:
    response = ask("X vs Y", {"kind": "compare", "companies": ["Nope Corp", "Also Nope"]})

    assert response.status_code == 422
    assert "Couldn't find" in response.json()["detail"]["errors"][0]


def test_a_breakdown_counts_from_the_data() -> None:
    body = ask("by verdict", {"kind": "breakdown", "measure": "count", "by": "verdict"}).json()

    # The owner sees every domain and their own overrule: all four are fits.
    assert dict(zip(body["categories"], body["series"][0]["values"])) == {"Fits": 4}


def test_a_breakdown_by_month_is_a_line_in_date_order() -> None:
    plans.append({"kind": "breakdown", "measure": "total_raise", "by": "month", "filters": {"domain": "AI infra"}})
    body = client.post("/api/charts", json={"question": "raises by month"}, headers=OWNER).json()

    assert body["categories"] == ["2026-08", "2026-09"]
    assert body["unit"] == "usd"


def test_top_ranks_by_the_measure_asked_for() -> None:
    body = ask("top 2", {"kind": "top", "top_measure": "raise", "limit": 2}).json()

    assert body["categories"] == ["Tenstorrent Holdings", "Fab2, Inc."]


def test_a_ranking_is_of_fits_unless_asked_otherwise() -> None:
    body = ask("top 10", {"kind": "top", "top_measure": "raise", "limit": 10}, headers=VISITOR).json()

    # Small Co is a no fit to a visitor (the owner's overrule is private), so it is left out.
    assert "Small Co" not in body["categories"]
    assert body["subtitle"].startswith("Fits")


def test_a_ranking_of_everything_when_asked() -> None:
    body = ask(
        "top 10 of everything",
        {"kind": "top", "top_measure": "raise", "filters": {"verdicts": ["fits", "maybe", "unknown", "no_fit"]}},
        headers=VISITOR,
    ).json()

    assert "Small Co" in body["categories"]
    assert "all verdicts" in body["subtitle"]


def test_a_ranking_shows_each_companys_verdict() -> None:
    body = ask("top 3", {"kind": "top", "top_measure": "raise", "limit": 3, "filters": {"domain": "AI infra"}}).json()

    assert body["colour_by"] == "verdict"
    assert body["marks"] == ["Fits", "Fits", "Fits"]  # owner sees their own overrule on Small Co


# --- what a visitor's chart may contain -------------------------------------------

def test_a_visitors_chart_leaves_out_private_domains() -> None:
    body = ask("top 10", {"kind": "top", "top_measure": "raise", "limit": 10}, headers=VISITOR).json()

    assert "Hidden Co" not in body["categories"]


def test_naming_a_private_domain_does_not_open_it() -> None:
    body = ask(
        "parallax raises",
        {"kind": "top", "top_measure": "raise", "filters": {"domain": "Parallax"}},
        headers=VISITOR,
    ).json()

    assert "Hidden Co" not in body["categories"]


def test_a_visitor_counts_the_models_verdict_not_the_owners() -> None:
    body = ask("by verdict", {"kind": "breakdown", "by": "verdict"}, headers=VISITOR).json()
    counts = dict(zip(body["categories"], body["series"][0]["values"]))

    assert counts["No fit"] == 1  # the owner overruled Small Co to fits; a visitor never sees that


def test_a_visitor_cannot_compare_against_a_hidden_company() -> None:
    response = ask("Tenstorrent vs Hidden", {"kind": "compare", "companies": ["Tenstorrent", "Hidden Co"]}, headers=VISITOR)

    assert response.status_code == 422


def test_visitors_are_limited(monkeypatch) -> None:
    monkeypatch.setattr(charts_module, "CHARTS_PER_HOUR", 1)
    ask("top", {"kind": "top"}, headers=VISITOR)

    response = ask("top", {"kind": "top"}, headers=VISITOR)

    assert response.status_code == 429


# --- what the model may ask for ----------------------------------------------------

def test_nulls_from_the_model_mean_not_applicable() -> None:
    body = ask("by verdict", {
        "kind": "breakdown", "companies": [], "measure": "count", "by": "verdict",
        "filters": {"domain": None, "verdicts": None, "since": None},
    }).json()

    assert body["categories"] == ["Fits"]


def test_an_empty_field_from_the_model_means_not_applicable() -> None:
    body = ask("top 2", {"kind": "top", "by": "", "measure": "count", "top_measure": "raise", "limit": 2}).json()

    assert body["categories"] == ["Tenstorrent Holdings", "Fab2, Inc."]


def test_a_compare_with_null_filters_still_works() -> None:
    body = ask("Tenstorrent vs Fab2", {"kind": "compare", "companies": ["Tenstorrent", "Fab2"], "filters": None}).json()

    assert body["form"] == "grouped"


def test_a_plan_outside_the_choices_is_refused() -> None:
    response = ask("drop tables", {"kind": "sql", "query": "DROP TABLE candidate"})

    assert response.status_code == 422


def test_a_measure_outside_the_choices_is_refused() -> None:
    response = ask("x", {"kind": "breakdown", "measure": "user_note", "by": "verdict"})

    assert response.status_code == 422


def test_an_unsupported_question_explains_what_is_possible() -> None:
    response = ask("what's the weather", {"kind": "unsupported", "reason": "Not about the data."})

    message = response.json()["detail"]["errors"][0]

    assert "Not about the data" in message
    assert "compare companies" in message


def test_a_model_failure_is_reported_as_unavailable(monkeypatch) -> None:
    def broken(system, user):
        raise RuntimeError("402 Payment Required")

    monkeypatch.setattr(api_module, "chart_planner", lambda: broken)

    response = client.post("/api/charts", json={"question": "top 10"}, headers=OWNER)

    assert response.status_code == 503
