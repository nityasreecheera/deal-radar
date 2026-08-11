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


def test_chat_is_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    # Every question costs money and this can be published behind one shared
    # password, so a runaway must become a refusal rather than a bill.
    monkeypatch.setattr(api_module, "CHAT_LIMIT_PER_HOUR", 2)
    monkeypatch.setattr(api_module, "_chat_times", api_module.deque())
    monkeypatch.setattr(
        "src.chat.create_chat_client", lambda: (lambda s, u: "an answer")
    )

    for _ in range(2):
        assert client.post("/api/chat", json={"question": "hi?"}).status_code == 200

    third = client.post("/api/chat", json={"question": "hi?"})

    assert third.status_code == 429
    assert "limit is 2" in third.json()["detail"]["errors"][0]


def test_a_refused_question_does_not_consume_allowance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A question rejected by validation never reaches the model, so it should not
    # count against a budget that exists to cap spending.
    monkeypatch.setattr(api_module, "CHAT_LIMIT_PER_HOUR", 1)
    monkeypatch.setattr(api_module, "_chat_times", api_module.deque())
    monkeypatch.setattr(
        "src.chat.create_chat_client", lambda: (lambda s, u: "an answer")
    )

    assert client.post("/api/chat", json={"question": "x" * 501}).status_code == 422
    assert client.post("/api/chat", json={"question": "hi?"}).status_code == 200


def test_detail_includes_funding_history_and_progress(isolated: Path) -> None:
    from src.funding import FundingHistory, FundingRound, save_history

    seed(candidate(amount=2_000_000))

    with connect() as connection:
        connection.execute(
            "UPDATE candidate SET cik = '1234567', amount_sold = 1699999"
        )
        connection.commit()

        save_history(
            connection,
            FundingHistory(
                cik="1234567",
                rounds=[
                    FundingRound(
                        accession="old",
                        cik="1234567",
                        filed_date="2023-07-20",
                        offering_amount=1_000_000,
                        amount_sold=1_000_000,
                    ),
                    FundingRound(
                        accession="acc-1",
                        cik="1234567",
                        filed_date="2026-07-30",
                        offering_amount=2_000_000,
                        amount_sold=1_699_999,
                    ),
                ],
            ),
        )

    body = client.get("/api/candidates/acc-1/detail").json()

    assert len(body["rounds"]) == 2
    assert body["is_first_raise"] is False
    assert "2 raises on record" in body["funding_summary"]
    # The real PreventiveMD ratio.
    assert body["progress_percent"] == 85
    assert "nearly closed" in body["progress_note"]


def test_detail_of_a_company_with_no_history(isolated: Path) -> None:
    seed(candidate())

    body = client.get("/api/candidates/acc-1/detail").json()

    # No history stored is not an error, and a lone company is a first raise.
    assert body["rounds"] == []
    assert body["is_first_raise"] is True
    assert body["shared_people"] == []


def test_detail_of_an_unknown_company_is_404() -> None:
    assert client.get("/api/candidates/nope/detail").status_code == 404


def test_detail_reports_shared_people(isolated: Path) -> None:
    from src.models import RelatedPerson

    shared = [RelatedPerson(first_name="Kenneth", last_name="Gall")]

    for accession, name in (("acc-1", "Huxley Medical"), ("acc-2", "Protect3d")):
        item = candidate(name=name, accession=accession)
        item.filing.related_persons = shared
        seed(item)

    body = client.get("/api/candidates/acc-1/detail").json()

    assert len(body["shared_people"]) == 1
    assert body["shared_people"][0]["full_name"] == "Kenneth Gall"
    assert body["shared_people"][0]["other_companies"] == ["Protect3d"]


def test_people_endpoint_lists_only_repeat_appearances(isolated: Path) -> None:
    from src.models import RelatedPerson

    for accession, name in (("acc-1", "A Inc"), ("acc-2", "B Inc")):
        item = candidate(name=name, accession=accession)
        item.filing.related_persons = [
            RelatedPerson(first_name="Kenneth", last_name="Gall")
        ]
        seed(item)

    solo = candidate(name="C Inc", accession="acc-3")
    solo.filing.related_persons = [
        RelatedPerson(first_name="Solo", last_name="Founder")
    ]
    seed(solo)

    body = client.get("/api/people").json()

    assert body == [{"full_name": "Kenneth Gall", "companies": 2}]


def test_saving_a_note_over_http() -> None:
    seed(candidate())

    response = client.post(
        "/api/candidates/acc-1/decision",
        json={"note": "Founder was vague on the clinical data."},
    )

    assert response.status_code == 200
    assert response.json()["user_note"] == (
        "Founder was vague on the clinical data."
    )


def test_overriding_a_verdict_over_http() -> None:
    seed(candidate(verdict="no_fit"))

    body = client.post(
        "/api/candidates/acc-1/decision",
        json={"verdict": "fits"},
    ).json()

    # The model's answer stays on the record; the analyst's wins.
    assert body["verdict"] == "no_fit"
    assert body["user_verdict"] == "fits"
    assert body["effective_verdict"] == "fits"
    assert body["overridden"] is True


def test_the_computed_verdict_reaches_the_browser() -> None:
    # A @property is not serialised by Pydantic, which has silently dropped
    # fields before. These are computed_fields precisely so they cross the wire.
    seed(candidate())

    body = client.get("/api/candidates").json()

    row = body["candidates"][0] if isinstance(body, dict) else body[0]

    assert "effective_verdict" in row
    assert "overridden" in row


def test_an_overridden_company_is_filtered_under_its_new_verdict() -> None:
    seed(candidate(name="Rescued Co", accession="acc-1", verdict="no_fit"))

    client.post("/api/candidates/acc-1/decision", json={"verdict": "fits"})

    body = client.get("/api/candidates?verdict=fits").json()
    rows = body["candidates"] if isinstance(body, dict) else body

    assert [r["company_name"] for r in rows] == ["Rescued Co"]


def test_clearing_a_verdict_over_http() -> None:
    seed(candidate(verdict="maybe"))
    client.post("/api/candidates/acc-1/decision", json={"verdict": "fits"})

    body = client.post(
        "/api/candidates/acc-1/decision",
        json={"clear_verdict": True},
    ).json()

    assert body["user_verdict"] is None
    assert body["effective_verdict"] == "maybe"


def test_the_disagreements_endpoint_lists_overrides() -> None:
    seed(
        candidate(name="Overruled Co", accession="acc-1", verdict="no_fit"),
        candidate(name="Agreed Co", accession="acc-2", verdict="fits"),
    )

    client.post("/api/candidates/acc-1/decision", json={"verdict": "fits"})
    client.post("/api/candidates/acc-2/decision", json={"verdict": "fits"})

    rows = client.get("/api/disagreements").json()

    assert [r["company_name"] for r in rows] == ["Overruled Co"]


def test_a_decision_on_a_company_that_does_not_exist_is_a_404() -> None:
    response = client.post(
        "/api/candidates/nope/decision",
        json={"note": "x"},
    )

    assert response.status_code == 404


def test_a_nonsense_verdict_is_rejected() -> None:
    seed(candidate())

    response = client.post(
        "/api/candidates/acc-1/decision",
        json={"verdict": "brilliant"},
    )

    assert response.status_code == 422
