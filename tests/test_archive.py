"""
The archive: every Form D, stored without judging any of it.

What matters most here is the difference between a day with nothing filed and
a day nobody read. Both hold no rows; only the day record tells them apart.
"""

import json
from contextlib import closing
from pathlib import Path

import pytest

from src.archive import (
    FUND_GROUP,
    archive_range,
    archived_filings,
    coverage,
    days_between,
    outcome_from_archive,
)
from src.edgar import SearchOutcome, build_search_url, fetch_filings
from src.models import FormDFiling
from src.seen import connect


FIXTURES = Path(__file__).parent / "fixtures"


def filing(name: str, group: str = "Other Technology", filed: str = "2026-09-01") -> FormDFiling:
    return FormDFiling(
        accession=f"acc-{name}",
        cik="1",
        company_name=name,
        filed_date=filed,
        industry_group=group,
        total_offering_amount=5_000_000,
    )


def edgar(by_day: dict[str, list[FormDFiling]], problems: dict[str, list[str]] | None = None):
    """A stand-in for fetch_filings that answers from a table, one day at a time."""
    asked: list[tuple] = []

    def fetch(start, end, industry_groups=None, max_per_group=None):
        asked.append((start, end, industry_groups))

        return SearchOutcome(
            list(by_day.get(start, [])),
            list((problems or {}).get(start, [])),
            [],
            ["all Form D"],
        )

    fetch.asked = asked

    return fetch


@pytest.fixture
def db(tmp_path: Path):
    with closing(connect(tmp_path / "radar.sqlite")) as connection:
        yield connection


# --- asking EDGAR for everything -------------------------------------------

def test_the_broad_search_asks_for_no_phrase() -> None:
    url = build_search_url(None, "2026-09-01", "2026-09-01")

    assert "q=" not in url
    assert "forms=D" in url


def test_the_broad_fetch_keeps_a_filing_in_any_group() -> None:
    xml = (FIXTURES / "preventivemd_form_d.xml").read_text(encoding="utf-8").replace(
        "Other Health Care", FUND_GROUP
    )
    searches: list[str] = []

    def fake_fetch(url: str) -> str:
        if url.startswith("https://efts.sec.gov"):
            searches.append(url)

            return json.dumps(
                {
                    "hits": {
                        "total": {"value": 1},
                        "hits": [
                            {
                                "_id": "0002147093-26-000001:primary_doc.xml",
                                "_source": {"ciks": ["0002147093"], "file_date": "2026-09-01"},
                            }
                        ],
                    }
                }
            )

        return xml

    outcome = fetch_filings("2026-09-01", "2026-09-01", industry_groups=None, fetch=fake_fetch)

    assert len(searches) == 1
    assert "q=" not in searches[0]
    assert [f.industry_group for f in outcome.filings] == [FUND_GROUP]
    assert outcome.searched == ["all Form D"]


def test_stopping_at_the_cap_is_reported_not_silent() -> None:
    def fake_fetch(url: str) -> str:
        if url.startswith("https://efts.sec.gov"):
            return json.dumps(
                {
                    "hits": {
                        "total": {"value": 25},
                        "hits": [
                            {
                                "_id": f"0000000001-26-{n:06d}:primary_doc.xml",
                                "_source": {"ciks": ["1"], "file_date": "2026-09-01"},
                            }
                            for n in range(10)
                        ],
                    }
                }
            )

        return "<broken"

    outcome = fetch_filings(
        "2026-09-01", "2026-09-01", industry_groups=None, fetch=fake_fetch, max_per_group=10
    )

    assert any("cap of 10 of 25" in problem for problem in outcome.problems)


# --- storing it -------------------------------------------------------------

def test_every_day_in_the_range_is_read_and_recorded(db) -> None:
    fetch = edgar({"2026-09-01": [filing("Acme")], "2026-09-02": []})

    run = archive_range(db, "2026-09-01", "2026-09-03", fetch_filings=fetch)

    assert [day for day, _, groups in fetch.asked] == ["2026-09-01", "2026-09-02", "2026-09-03"]
    assert all(groups is None for _, _, groups in fetch.asked)
    assert run.filings == 1
    assert coverage(db, "2026-09-01", "2026-09-03").missing == []


def test_a_fund_is_kept_and_marked(db) -> None:
    archive_range(
        db,
        "2026-09-01",
        "2026-09-01",
        fetch_filings=edgar({"2026-09-01": [filing("Big Fund LP", group=FUND_GROUP)]}),
    )

    row = db.execute("SELECT is_fund FROM archived_filing").fetchone()

    assert row["is_fund"] == 1


def test_reading_a_day_twice_does_not_store_it_twice(db) -> None:
    fetch = edgar({"2026-09-01": [filing("Acme")]})

    archive_range(db, "2026-09-01", "2026-09-01", fetch_filings=fetch)
    archive_range(db, "2026-09-01", "2026-09-01", fetch_filings=fetch)

    assert db.execute("SELECT COUNT(*) AS n FROM archived_filing").fetchone()["n"] == 1


def test_a_day_with_problems_is_stored_but_not_complete(db) -> None:
    run = archive_range(
        db,
        "2026-09-01",
        "2026-09-01",
        fetch_filings=edgar(
            {"2026-09-01": [filing("Acme")]},
            problems={"2026-09-01": ["acc-x: could not parse"]},
        ),
    )

    assert run.incomplete == ["2026-09-01"]
    assert len(archived_filings(db, "2026-09-01", "2026-09-01", ["Other Technology"])) == 1
    assert coverage(db, "2026-09-01", "2026-09-01").missing == ["2026-09-01"]


def test_a_later_full_read_completes_a_partial_day(db) -> None:
    archive_range(
        db, "2026-09-01", "2026-09-01",
        fetch_filings=edgar({}, problems={"2026-09-01": ["search failed"]}),
    )
    archive_range(db, "2026-09-01", "2026-09-01", fetch_filings=edgar({"2026-09-01": [filing("Acme")]}))

    assert coverage(db, "2026-09-01", "2026-09-01").is_complete


def test_a_later_partial_read_does_not_undo_a_complete_day(db) -> None:
    archive_range(db, "2026-09-01", "2026-09-01", fetch_filings=edgar({"2026-09-01": [filing("Acme")]}))
    archive_range(
        db, "2026-09-01", "2026-09-01",
        fetch_filings=edgar({}, problems={"2026-09-01": ["search failed"]}),
    )

    assert coverage(db, "2026-09-01", "2026-09-01").is_complete


# --- reading it back --------------------------------------------------------

def test_reading_back_keeps_only_the_groups_and_dates_asked_for(db) -> None:
    archive_range(
        db,
        "2026-09-01",
        "2026-09-02",
        fetch_filings=edgar(
            {
                "2026-09-01": [filing("Tech", filed="2026-09-01"), filing("Fund", group=FUND_GROUP)],
                "2026-09-02": [filing("Later", filed="2026-09-02")],
            }
        ),
    )

    found = archived_filings(db, "2026-09-01", "2026-09-01", ["Other Technology"])

    assert [f.company_name for f in found] == ["Tech"]


def test_a_filing_comes_back_whole(db) -> None:
    original = filing("Acme").model_copy(update={"investor_count": 7, "city": "AUSTIN"})
    archive_range(db, "2026-09-01", "2026-09-01", fetch_filings=edgar({"2026-09-01": [original]}))

    assert archived_filings(db, "2026-09-01", "2026-09-01", ["Other Technology"]) == [original]


def test_an_unread_day_in_the_range_is_reported_to_the_pipeline(db) -> None:
    archive_range(db, "2026-09-01", "2026-09-01", fetch_filings=edgar({"2026-09-01": [filing("Acme")]}))

    outcome = outcome_from_archive(db, "2026-09-01", "2026-09-02", ["Other Technology"])

    assert len(outcome.filings) == 1
    assert len(outcome.problems) == 1
    assert "2026-09-02" in outcome.problems[0]


def test_a_fully_read_range_reports_no_problem(db) -> None:
    archive_range(db, "2026-09-01", "2026-09-02", fetch_filings=edgar({}))

    assert outcome_from_archive(db, "2026-09-01", "2026-09-02", ["Other Technology"]).problems == []


def test_days_between_includes_both_ends() -> None:
    assert days_between("2026-09-30", "2026-10-02") == ["2026-09-30", "2026-10-01", "2026-10-02"]
