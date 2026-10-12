"""
The public site: what a visitor can read, and what stays the owner's.

A visitor is anyone the proxy marks `public`. They read judgements and reasons.
They must not see a private domain, the owner's own verdicts and notes, or
anything that writes or spends money — and these tests ask for each of those
directly, because a page hiding a button is not the same as the data being gone.
"""

from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.api as api_module
import src.seen as seen_module
import src.visibility as visibility_module
from src.api import app
from src.candidates import record_decision, record_outreach, save_candidate
from src.models import Candidate, FormDFiling
from src.seen import connect
from src.thesis import Thesis


client = TestClient(app)
PUBLIC = {"x-radar-viewer": "public"}


def thesis(domain: str, public: bool = True) -> Thesis:
    return Thesis.model_validate(
        {
            "domain": domain,
            "name": f"{domain} criteria",
            "description": "Anything.",
            "include": ["anything"],
            "public": public,
        }
    )


def candidate(name: str, accession: str, verdict: str = "fits") -> Candidate:
    return Candidate(
        filing=FormDFiling(
            accession=accession,
            cik="1",
            company_name=name,
            filed_date="2026-09-01",
            industry_group="Other Technology",
            total_offering_amount=5_000_000,
        ),
        verdict=verdict,
        reason="Because.",
        description="They make things.",
    )


@pytest.fixture(autouse=True)
def site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Two domains, one private; a judgement in each; the owner's note on both."""
    monkeypatch.setattr(seen_module, "DEFAULT_DB_PATH", tmp_path / "radar.sqlite")
    monkeypatch.setattr(api_module, "DIGEST_DIR", tmp_path / "digests")

    theses = [thesis("Healthcare"), thesis("Parallax", public=False)]
    monkeypatch.setattr(visibility_module, "load_all_theses", lambda: theses)
    monkeypatch.setattr(api_module, "available_themes", lambda: ["Healthcare", "Parallax"])

    # A paid call must never happen for a visitor; make one fail loudly if it does.
    def no_spending(*args, **kwargs):
        raise AssertionError("a visitor triggered a paid model call")

    monkeypatch.setattr(api_module, "write_profile", no_spending)

    with closing(connect()) as connection:
        save_candidate(connection, candidate("Open Co", "acc-open"), theme="Healthcare")
        save_candidate(connection, candidate("Secret Co", "acc-secret"), theme="Parallax")
        record_decision(connection, "acc-open", verdict="no_fit", note="Met the founder; passing.")
        record_outreach(connection, "acc-open", status="emailed", email="ceo@open.co")


# --- what a visitor reads ---------------------------------------------------

def test_a_visitor_sees_only_public_domains() -> None:
    meta = client.get("/api/meta", headers=PUBLIC).json()

    assert meta["themes"] == ["Healthcare"]
    assert meta["viewer"] == "public"
    assert meta["digest_dates"] == []


def test_a_visitor_lists_no_judgement_from_a_private_domain() -> None:
    names = [c["company_name"] for c in client.get("/api/candidates", headers=PUBLIC).json()["candidates"]]

    assert names == ["Open Co"]


def test_asking_for_a_private_domain_by_name_returns_nothing() -> None:
    body = client.get("/api/candidates", params={"theme": "Parallax"}, headers=PUBLIC).json()

    assert body["candidates"] == []


def test_a_private_company_page_is_not_found_for_a_visitor() -> None:
    assert client.get("/api/candidates/acc-secret", headers=PUBLIC).status_code == 404
    assert client.get("/api/candidates/acc-secret/detail", headers=PUBLIC).status_code == 404


def test_a_visitor_sees_the_models_verdict_not_the_owners() -> None:
    found = client.get("/api/candidates/acc-open", headers=PUBLIC).json()

    assert found["verdict"] == "fits"
    assert found["user_verdict"] is None
    assert found["user_note"] is None
    assert found["contact_email"] is None
    assert found["outreach_status"] is None


def test_the_owners_verdict_does_not_change_what_a_visitor_filters_on() -> None:
    # The owner overruled Open Co to no_fit. A visitor filtering on fits still
    # finds it, because for them the model's verdict is the only one.
    body = client.get("/api/candidates", params={"verdict": "fits"}, headers=PUBLIC).json()

    assert [c["company_name"] for c in body["candidates"]] == ["Open Co"]


def test_opening_a_company_never_spends_money_for_a_visitor() -> None:
    body = client.get("/api/candidates/acc-open/profile", headers=PUBLIC).json()

    assert body["profile"] is None
    assert body["fallback"] == "They make things."


def test_the_analysis_leaves_out_private_domains() -> None:
    domains = [row["domain"] for row in client.get("/api/analysis", headers=PUBLIC).json()["domains"]]

    assert "Parallax" not in domains


# --- what a visitor cannot do -------------------------------------------------

@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/theses"),
        ("get", "/api/disagreements"),
        ("get", "/api/digests"),
        ("get", "/api/runs"),
        ("get", "/api/theses/Healthcare/run-preview?start_date=2026-09-01&end_date=2026-09-01"),
        ("post", "/api/chat"),
        ("post", "/api/viewed"),
        ("post", "/api/candidates/acc-open/viewed"),
        ("post", "/api/candidates/acc-open/decision"),
        ("post", "/api/theses/Healthcare/runs"),
        ("delete", "/api/theses/Healthcare"),
    ],
)
def test_a_visitor_is_refused_anything_that_writes_spends_or_shows_strategy(method, path) -> None:
    response = getattr(client, method)(path, headers=PUBLIC, **({"json": {}} if method == "post" else {}))

    assert response.status_code == 403


def test_nothing_a_visitor_did_reached_the_owners_record() -> None:
    client.post("/api/candidates/acc-open/decision", json={"verdict": "fits"}, headers=PUBLIC)

    owner = client.get("/api/candidates/acc-open").json()

    assert owner["user_verdict"] == "no_fit"


# --- the owner, and the API's own default -------------------------------------

def test_the_owner_still_sees_everything() -> None:
    meta = client.get("/api/meta", headers={"x-radar-viewer": "owner"}).json()
    found = client.get("/api/candidates/acc-open").json()

    assert meta["themes"] == ["Healthcare", "Parallax"]
    assert found["user_note"] == "Met the founder; passing."


def test_an_unknown_viewer_value_is_not_treated_as_public_or_trusted_elsewhere() -> None:
    # Only the proxy sets this header, and it always overwrites it. A value it
    # never sends falls back to the API's default for a local caller.
    assert client.get("/api/viewer", headers={"x-radar-viewer": "admin"}).json() == {"viewer": "owner"}


def test_a_reader_token_still_reads_private_domains() -> None:
    meta = client.get("/api/meta", headers={"x-radar-viewer": "reader"}).json()

    assert "Parallax" in meta["themes"]
