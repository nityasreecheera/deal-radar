"""
Runs started from the website, against the archive.

Two things are worth proving beyond "it runs". It cannot spend more than it says
— the cap holds, and only one run goes at a time. And a run where nothing could
be examined is never reported as a run where nothing was found.
"""

from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.api as api_module
import src.pipeline as pipeline_module
import src.runs as runs_module
import src.seen as seen_module
from src.api import app
from src.archive import save_filing, record_day, ArchivedDay
from src.enrich import Enrichment
from src.models import Candidate, FormDFiling
from src.runs import (
    MAX_CAP,
    RunInProgress,
    RunRequest,
    execute_run,
    get_run,
    preview,
    start_run,
)
from src.seen import connect, mark_seen_for_theme
from src.thesis import Thesis


client = TestClient(app)


def thesis() -> Thesis:
    return Thesis.model_validate(
        {
            "domain": "AI tools",
            "name": "AI software",
            "description": "Software other developers build with.",
            "include": ["developer tooling"],
            "filters": {"min_offering_amount": 100_000},
            "sec_industry_groups": ["Other Technology"],
        }
    )


def filing(name: str, group: str = "Other Technology", amount: int = 5_000_000) -> FormDFiling:
    return FormDFiling(
        accession=f"acc-{name}",
        cik="1",
        company_name=name,
        filed_date="2026-09-01",
        industry_group=group,
        total_offering_amount=amount,
    )


def judge(verdict: str = "fits"):
    def run(f: FormDFiling, e: Enrichment, t: Thesis) -> Candidate:
        return Candidate(filing=f, verdict=verdict, reason="Fits.", description=e.description)

    return run


def enrich(f: FormDFiling) -> Enrichment:
    return Enrichment(website="https://example.com", description="Developer tooling.")


def broken_enrich(f: FormDFiling) -> Enrichment:
    raise RuntimeError("usage limit exceeded")


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A temporary database, and one domain the API knows about."""
    monkeypatch.setattr(seen_module, "DEFAULT_DB_PATH", tmp_path / "radar.sqlite")
    monkeypatch.setattr(api_module, "load_all_theses", lambda: [thesis()])

    # A company that fits has its funding history fetched from EDGAR. Offline
    # here, like every other test.
    monkeypatch.setattr(pipeline_module, "fetch_history", lambda cik: [])

    return tmp_path


def archive(*filings: FormDFiling, day: str = "2026-09-01") -> None:
    with closing(connect()) as connection:
        for f in filings:
            save_filing(connection, f)

        record_day(connection, ArchivedDay(day=day, filings=len(filings)))
        connection.commit()


def request(cap: int = MAX_CAP) -> RunRequest:
    return RunRequest(start_date="2026-09-01", end_date="2026-09-01", cap=cap)


def run_inline(run_id: int, enrich_with=enrich, judge_with=None) -> None:
    execute_run(run_id, thesis(), enrich=enrich_with, judge=judge_with or judge())


# --- what may be asked for ---------------------------------------------------

@pytest.mark.parametrize(
    ("start", "end", "cap", "message"),
    [
        ("2026-09-02", "2026-09-01", 10, "after the end"),
        ("2026-09-01", "2999-01-01", 10, "future"),
        ("2024-01-01", "2026-09-01", 10, "at most"),
        ("2026-09-01", "2026-09-01", MAX_CAP + 1, "at most"),
        ("1 Sept", "2026-09-01", 10, "YYYY-MM-DD"),
    ],
)
def test_a_bad_request_is_refused_with_a_reason(start, end, cap, message) -> None:
    with pytest.raises(ValueError, match=message):
        RunRequest(start_date=start, end_date=end, cap=cap)


# --- the preview -------------------------------------------------------------

def test_the_preview_counts_without_judging_anything() -> None:
    archive(
        filing("Fresh One"),
        filing("Fresh Two"),
        filing("Seen Before"),
        filing("Tiny", amount=10),
        filing("Some Fund", group="Pooled Investment Fund"),
    )

    with closing(connect()) as connection:
        mark_seen_for_theme(connection, "Seen Before", "AI tools")
        result = preview(connection, thesis(), request())
        judged = connection.execute("SELECT COUNT(*) AS n FROM candidate").fetchone()["n"]

    assert result.archived == 4  # the fund is in another group
    assert result.passed_filters == 3  # the tiny raise is under the floor
    assert result.already_checked == 1
    assert result.to_check == 2
    assert result.model_calls == 2
    assert result.lookups == 2
    assert result.missing_days == []
    assert judged == 0


def test_the_preview_shows_what_the_cap_leaves_for_later() -> None:
    archive(*(filing(f"Company {n}") for n in range(5)))

    with closing(connect()) as connection:
        result = preview(connection, thesis(), request(cap=2))

    assert result.to_check == 2
    assert result.left_over == 3


def test_the_preview_names_days_the_archive_has_not_read() -> None:
    archive(filing("Acme"))

    with closing(connect()) as connection:
        result = preview(
            connection,
            thesis(),
            RunRequest(start_date="2026-09-01", end_date="2026-09-03"),
        )

    assert result.missing_days == ["2026-09-02", "2026-09-03"]


# --- running -----------------------------------------------------------------

def test_a_run_judges_and_records_what_it_found() -> None:
    archive(filing("Acme"), filing("Beta"))

    with closing(connect()) as connection:
        run = start_run(connection, thesis(), request())

    run_inline(run.id)

    with closing(connect()) as connection:
        finished = get_run(connection, run.id)
        themes = {row["theme"] for row in connection.execute("SELECT theme FROM candidate")}

    assert finished.status == "done"
    assert finished.judged == 2
    assert finished.fits == 2
    assert finished.message == "Judged 2."
    assert themes == {"AI tools"}


def test_a_run_never_judges_more_than_its_cap() -> None:
    archive(*(filing(f"Company {n}") for n in range(5)))

    with closing(connect()) as connection:
        run = start_run(connection, thesis(), request(cap=2))

    run_inline(run.id)

    with closing(connect()) as connection:
        assert get_run(connection, run.id).judged == 2
        assert connection.execute("SELECT COUNT(*) AS n FROM candidate").fetchone()["n"] == 2


def test_a_company_judged_once_is_not_judged_again() -> None:
    archive(filing("Acme"))

    for _ in range(2):
        with closing(connect()) as connection:
            run = start_run(connection, thesis(), request())

        run_inline(run.id)

    with closing(connect()) as connection:
        assert get_run(connection, run.id).judged == 0
        assert get_run(connection, run.id).message == "Nothing new to judge in this range."


def test_a_run_that_examined_nothing_does_not_say_nothing_was_found() -> None:
    archive(filing("Acme"), filing("Beta"))

    with closing(connect()) as connection:
        run = start_run(connection, thesis(), request())

    run_inline(run.id, enrich_with=broken_enrich)

    with closing(connect()) as connection:
        finished = get_run(connection, run.id)

    assert finished.status == "done"
    assert finished.judged == 0
    assert finished.unexamined == 2
    assert "None of the 2 companies could be examined" in finished.message
    assert any("usage limit exceeded" in p for p in finished.problems)


def test_a_run_that_crashes_is_marked_failed_with_the_reason(monkeypatch) -> None:
    def explode(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(runs_module, "run_radar", explode)

    with closing(connect()) as connection:
        run = start_run(connection, thesis(), request())

    run_inline(run.id)

    with closing(connect()) as connection:
        finished = get_run(connection, run.id)

    assert finished.status == "failed"
    assert "disk full" in finished.message


def test_only_one_run_goes_at_a_time() -> None:
    with closing(connect()) as connection:
        start_run(connection, thesis(), request())

        with pytest.raises(RunInProgress):
            start_run(connection, thesis(), request())


def test_a_run_left_running_by_a_restart_does_not_block_forever() -> None:
    with closing(connect()) as connection:
        stuck = start_run(connection, thesis(), request())
        hours_ago = (datetime.now(UTC) - timedelta(hours=5)).isoformat()
        connection.execute(
            "UPDATE manual_run SET requested_at = ? WHERE id = ?", (hours_ago, stuck.id)
        )
        connection.commit()

        start_run(connection, thesis(), request())

        assert get_run(connection, stuck.id).status == "failed"


# --- over HTTP -----------------------------------------------------------------

@pytest.fixture
def inline(monkeypatch):
    """Run in the request rather than on a thread, so the test can see the end."""
    monkeypatch.setattr(
        api_module, "launch", lambda run, t: run_inline(run.id)
    )


def test_the_preview_endpoint_answers() -> None:
    archive(filing("Acme"))

    response = client.get(
        "/api/theses/AI tools/run-preview",
        params={"start_date": "2026-09-01", "end_date": "2026-09-01"},
    )

    assert response.status_code == 200
    assert response.json()["to_check"] == 1


def test_an_unknown_domain_is_a_404() -> None:
    response = client.get(
        "/api/theses/Nope/run-preview",
        params={"start_date": "2026-09-01", "end_date": "2026-09-01"},
    )

    assert response.status_code == 404


def test_a_bad_range_is_a_422_with_a_readable_reason() -> None:
    response = client.post(
        "/api/theses/AI tools/runs",
        json={"start_date": "2026-09-05", "end_date": "2026-09-01"},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["errors"] == ["the start date is after the end date"]


def test_running_over_http_starts_and_reports(inline) -> None:
    archive(filing("Acme"))

    started = client.post(
        "/api/theses/AI tools/runs",
        json={"start_date": "2026-09-01", "end_date": "2026-09-01", "cap": 5},
    )

    assert started.status_code == 202

    finished = client.get(f"/api/runs/{started.json()['id']}").json()

    assert finished["status"] == "done"
    assert finished["judged"] == 1
    assert client.get("/api/runs").json()[0]["id"] == started.json()["id"]


def test_a_second_run_while_one_is_going_is_a_409(monkeypatch) -> None:
    monkeypatch.setattr(api_module, "launch", lambda run, t: None)  # never finishes
    body = {"start_date": "2026-09-01", "end_date": "2026-09-01"}

    assert client.post("/api/theses/AI tools/runs", json=body).status_code == 202
    assert client.post("/api/theses/AI tools/runs", json=body).status_code == 409


def test_an_unknown_run_is_a_404() -> None:
    assert client.get("/api/runs/999").status_code == 404
