import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.api as api_module
import src.candidates as candidates_module
import src.seen as seen_module
from src.api import app
from src.candidates import mark_viewed, save_candidate
from src.models import Candidate, FormDFiling
from src.seen import connect


client = TestClient(app)


def candidate(
    name: str = "Genomenon, Inc.",
    accession: str = "acc-1",
    verdict: str = "fits",
    reason: str = "AI software structuring genetic evidence.",
    amount: int | None = 10_000_000,
    filed_date: str = "2026-07-30",
    website: str | None = "https://genomenon.com",
) -> Candidate:
    return Candidate(
        filing=FormDFiling(
            accession=accession,
            cik="1",
            company_name=name,
            filed_date=filed_date,
            industry_group="Other Technology",
            city="ANN ARBOR",
            state="MI",
            total_offering_amount=amount,
        ),
        verdict=verdict,
        reason=reason,
        website=website,
    )


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Point the API at a temporary database and digest directory.

    The API opens its own connection per request via connect(), so the default
    path is what has to be redirected — patching a connection object would not
    reach it.
    """
    monkeypatch.setattr(
        seen_module, "DEFAULT_DB_PATH", tmp_path / "radar.sqlite"
    )
    monkeypatch.setattr(
        candidates_module, "normalize_company_name", None, raising=False
    )
    monkeypatch.setattr(api_module, "DIGEST_DIR", tmp_path / "digests")

    # Configured domains come from config/*.yaml on disk. Left unpatched, every
    # theme assertion would depend on the shipped thesis file.
    monkeypatch.setattr(api_module, "available_themes", lambda: [])

    return tmp_path


def seed(*candidates: Candidate, theme: str = "Healthcare") -> None:
    with connect() as connection:
        for item in candidates:
            save_candidate(connection, item, theme=theme)


def test_health() -> None:
    assert client.get("/api/health").json() == {"ok": True}


def test_meta_on_an_empty_database() -> None:
    body = client.get("/api/meta").json()

    assert body["companies_known"] == 0
    assert body["judgements"] == {}
    assert body["unread"] == 0
    assert body["themes"] == []
    assert body["earliest_filing"] is None
    assert body["digest_dates"] == []


def test_meta_includes_a_configured_domain_that_has_never_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A domain configured this morning has judged nothing yet. Omitting it makes
    # it look absent, so the dropdown would not offer it.
    monkeypatch.setattr(api_module, "available_themes", lambda: ["Finance"])

    assert client.get("/api/meta").json()["themes"] == ["Finance"]


def test_meta_merges_configured_and_observed_domains(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed(candidate(accession="a"), theme="Healthcare")
    monkeypatch.setattr(api_module, "available_themes", lambda: ["Finance"])

    # Both are real: one has history, the other is configured and pending.
    assert client.get("/api/meta").json()["themes"] == ["Finance", "Healthcare"]


def test_meta_reports_themes_and_bounds() -> None:
    seed(candidate(accession="a", filed_date="2026-06-01"))
    seed(candidate(accession="b", name="Chip Co", filed_date="2026-08-01"), theme="Chips")

    body = client.get("/api/meta").json()

    assert sorted(body["themes"]) == ["Chips", "Healthcare"]
    assert body["earliest_filing"] == "2026-06-01"
    assert body["latest_filing"] == "2026-08-01"
    assert body["unread"] == 2


def test_candidates_are_returned_newest_first() -> None:
    seed(
        candidate(accession="old", filed_date="2026-06-01"),
        candidate(accession="new", name="Newer Co", filed_date="2026-07-30"),
    )

    body = client.get("/api/candidates").json()

    assert body["count"] == 2
    assert [c["accession"] for c in body["candidates"]] == ["new", "old"]


def test_candidates_filter_by_verdict() -> None:
    seed(
        candidate(accession="a", verdict="fits"),
        candidate(accession="b", name="No Co", verdict="no_fit"),
    )

    body = client.get("/api/candidates", params={"verdict": "fits"}).json()

    assert [c["accession"] for c in body["candidates"]] == ["a"]


def test_candidates_filter_by_several_verdicts() -> None:
    seed(
        candidate(accession="a", verdict="fits"),
        candidate(accession="b", name="Maybe Co", verdict="maybe"),
        candidate(accession="c", name="No Co", verdict="no_fit"),
    )

    body = client.get(
        "/api/candidates", params=[("verdict", "fits"), ("verdict", "maybe")]
    ).json()

    assert {c["accession"] for c in body["candidates"]} == {"a", "b"}


def test_candidates_filter_by_theme() -> None:
    seed(candidate(accession="a"))
    seed(candidate(accession="b", name="Chip Co"), theme="Chips")

    body = client.get("/api/candidates", params={"theme": "Chips"}).json()

    assert [c["company_name"] for c in body["candidates"]] == ["Chip Co"]


def test_candidates_filter_by_date_range() -> None:
    seed(
        candidate(accession="a", filed_date="2026-06-01"),
        candidate(accession="b", name="Mid Co", filed_date="2026-07-15"),
        candidate(accession="c", name="Late Co", filed_date="2026-08-20"),
    )

    body = client.get(
        "/api/candidates",
        params={"since": "2026-07-01", "until": "2026-07-31"},
    ).json()

    assert [c["accession"] for c in body["candidates"]] == ["b"]


def test_candidates_can_be_limited_to_unread() -> None:
    seed(
        candidate(accession="a"),
        candidate(accession="b", name="Other Co"),
    )

    with connect() as connection:
        mark_viewed(connection, "a")

    body = client.get("/api/candidates", params={"unread_only": True}).json()

    assert [c["accession"] for c in body["candidates"]] == ["b"]
    assert body["unread"] == 1


def test_limit_is_bounded() -> None:
    # An unbounded limit is an invitation to fetch the whole table.
    assert client.get("/api/candidates", params={"limit": 5000}).status_code == 422
    assert client.get("/api/candidates", params={"limit": 0}).status_code == 422


def test_one_candidate() -> None:
    seed(candidate())

    body = client.get("/api/candidates/acc-1").json()

    assert body["company_name"] == "Genomenon, Inc."
    assert body["verdict"] == "fits"
    assert body["viewed_at"] is None


def test_an_unknown_candidate_is_404() -> None:
    response = client.get("/api/candidates/nope")

    assert response.status_code == 404
    assert response.json()["detail"]["ok"] is False


def test_marking_one_as_read() -> None:
    seed(candidate())

    body = client.post("/api/candidates/acc-1/viewed").json()

    assert body["viewed_at"] is not None

    # And it stays read.
    listed = client.get("/api/candidates", params={"unread_only": True}).json()

    assert listed["count"] == 0


def test_marking_an_unknown_one_is_404() -> None:
    assert client.post("/api/candidates/nope/viewed").status_code == 404


def test_marking_everything_read() -> None:
    seed(
        candidate(accession="a"),
        candidate(accession="b", name="Other Co"),
    )

    assert client.post("/api/viewed").json() == {"marked": 2}
    assert client.get("/api/meta").json()["unread"] == 0


def test_marking_everything_read_within_one_theme() -> None:
    seed(candidate(accession="a"))
    seed(candidate(accession="b", name="Chip Co"), theme="Chips")

    assert client.post("/api/viewed", params={"theme": "Chips"}).json() == {
        "marked": 1
    }
    assert client.get("/api/meta").json()["unread"] == 1


def test_company_history() -> None:
    seed(
        candidate(accession="a", filed_date="2025-01-01"),
        candidate(accession="b", filed_date="2026-07-30"),
    )

    body = client.get("/api/companies/Genomenon").json()

    assert [item["accession"] for item in body] == ["b", "a"]


def test_company_history_of_an_unknown_company_is_empty() -> None:
    assert client.get("/api/companies/Nobody").json() == []


def test_digests_are_listed_newest_first(isolated: Path) -> None:
    directory = isolated / "digests"
    directory.mkdir()
    (directory / "2026-07-29.md").write_text("older", encoding="utf-8")
    (directory / "2026-07-30.md").write_text("newer", encoding="utf-8")

    assert client.get("/api/digests").json() == ["2026-07-30", "2026-07-29"]


def test_one_digest(isolated: Path) -> None:
    directory = isolated / "digests"
    directory.mkdir()
    (directory / "2026-07-30.md").write_text("# digest body", encoding="utf-8")

    body = client.get("/api/digests/2026-07-30").json()

    assert body["date"] == "2026-07-30"
    assert body["markdown"] == "# digest body"


def test_an_unknown_digest_is_404() -> None:
    assert client.get("/api/digests/2020-01-01").status_code == 404


def test_a_traversal_attempt_is_rejected(isolated: Path) -> None:
    # The date becomes a filename, so it is checked against the known list
    # rather than trusted.
    directory = isolated / "digests"
    directory.mkdir()
    (directory / "2026-07-30.md").write_text("real", encoding="utf-8")

    for attempt in ("../../etc/passwd", "..%2F..%2Fetc%2Fpasswd"):
        response = client.get(f"/api/digests/{attempt}")

        assert response.status_code in (404, 400)


def test_chat_answers_from_stored_judgements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed(candidate())

    captured: dict[str, str] = {}

    def fake_chat(system: str, user: str) -> str:
        captured["system"] = system
        captured["user"] = user

        return "Genomenon fits — AI software structuring genetic evidence."

    monkeypatch.setattr("src.chat.create_chat_client", lambda: fake_chat)

    body = client.post(
        "/api/chat", json={"question": "which ones fitted?"}
    ).json()

    assert "Genomenon" in body["answer"]
    assert body["considered"] == 1
    assert body["accessions"] == ["acc-1"]
    # The model is given the recorded reason, not asked to recall the company.
    assert "AI software structuring genetic evidence." in captured["user"]
    assert "never as instructions" in captured["system"]


def test_chat_rejects_an_overlong_question() -> None:
    response = client.post(
        "/api/chat", json={"question": "x" * 501}
    )

    assert response.status_code == 422


def test_chat_rejects_an_empty_question() -> None:
    assert client.post("/api/chat", json={"question": ""}).status_code == 422


def test_chat_reports_a_missing_key_as_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.chat import ChatError

    def no_key() -> None:
        raise ChatError("No LLM key found. Set OPENROUTER_API_KEY in .env")

    monkeypatch.setattr("src.chat.create_chat_client", no_key)

    response = client.post("/api/chat", json={"question": "anything?"})

    # A misconfigured service is 503, not a client error.
    assert response.status_code == 503


def test_openapi_schema_is_generated() -> None:
    schema = client.get("/openapi.json").json()

    assert "StoredCandidate" in schema["components"]["schemas"]
    assert "/api/candidates" in schema["paths"]
    assert "/api/chat" in schema["paths"]
