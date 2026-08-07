import json
from contextlib import closing
from pathlib import Path

import pytest

from src.funding import (
    FundingHistory,
    FundingRound,
    fetch_history,
    load_history,
    parse_form_d_accessions,
    round_progress,
    save_history,
    submissions_url,
)
from src.seen import connect


def submissions(*filings) -> dict:
    """A submissions payload. Each filing is (form, date, accession)."""
    return {
        "filings": {
            "recent": {
                "form": [f[0] for f in filings],
                "filingDate": [f[1] for f in filings],
                "accessionNumber": [f[2] for f in filings],
            }
        }
    }


def form_d_xml(offering: int | None = 4_000_000, sold: int | None = 1_000_000) -> str:
    amounts = ""

    if offering is not None or sold is not None:
        amounts = "<offeringSalesAmounts>"
        if offering is not None:
            amounts += f"<totalOfferingAmount>{offering}</totalOfferingAmount>"
        if sold is not None:
            amounts += f"<totalAmountSold>{sold}</totalAmountSold>"
        amounts += "</offeringSalesAmounts>"

    return f"""<?xml version="1.0"?>
<edgarSubmission>
  <primaryIssuer>
    <cik>0001234567</cik>
    <entityName>Acme Health, Inc.</entityName>
  </primaryIssuer>
  <offeringData>
    <industryGroup><industryGroupType>Other Health Care</industryGroupType></industryGroup>
    {amounts}
  </offeringData>
</edgarSubmission>"""


@pytest.fixture
def db(tmp_path: Path):
    with closing(connect(tmp_path / "radar.sqlite")) as connection:
        yield connection


def test_submissions_url_pads_the_cik() -> None:
    assert submissions_url("1234567").endswith("CIK0001234567.json")
    # Leading zeros in, same thing out.
    assert submissions_url("0001234567") == submissions_url("1234567")


def test_only_form_d_filings_are_taken() -> None:
    payload = submissions(
        ("10-K", "2025-01-01", "a"),
        ("D", "2023-07-20", "b"),
        ("8-K", "2024-01-01", "c"),
        ("D/A", "2026-06-10", "d"),
    )

    found = parse_form_d_accessions(payload)

    assert [f[0] for f in found] == ["b", "d"]


def test_filings_come_back_oldest_first() -> None:
    payload = submissions(
        ("D", "2026-06-11", "new"),
        ("D", "2023-07-20", "old"),
    )

    assert [f[0] for f in parse_form_d_accessions(payload)] == ["old", "new"]


def test_amendments_are_flagged() -> None:
    payload = submissions(("D", "2026-01-21", "a"), ("D/A", "2026-06-10", "b"))

    found = parse_form_d_accessions(payload)

    assert found[0][2] is False
    assert found[1][2] is True


def test_an_empty_submissions_payload_is_not_a_crash() -> None:
    assert parse_form_d_accessions({}) == []
    assert parse_form_d_accessions({"filings": {}}) == []


def test_fetch_history_builds_rounds_with_amounts() -> None:
    def fake_fetch(url: str) -> str:
        if "submissions" in url:
            return json.dumps(
                submissions(
                    ("D", "2023-07-20", "0001-23-000001"),
                    ("D", "2026-06-11", "0001-26-000002"),
                )
            )

        return form_d_xml(offering=5_000_000, sold=5_000_000)

    history = fetch_history("1234567", fetch=fake_fetch)

    assert len(history.rounds) == 2
    assert history.first_raise.filed_date == "2023-07-20"
    assert history.latest.filed_date == "2026-06-11"
    assert history.is_first_time is False


def test_a_single_filing_is_a_first_raise() -> None:
    def fake_fetch(url: str) -> str:
        if "submissions" in url:
            return json.dumps(submissions(("D", "2026-06-12", "0001-26-000001")))

        return form_d_xml()

    history = fetch_history("1234567", fetch=fake_fetch)

    assert history.is_first_time is True
    assert "First raise on record" in history.describe()


def test_one_unreadable_filing_does_not_lose_the_history() -> None:
    def fake_fetch(url: str) -> str:
        if "submissions" in url:
            return json.dumps(
                submissions(
                    ("D", "2023-07-20", "0001-23-000001"),
                    ("D", "2026-06-11", "0001-26-000002"),
                )
            )

        if "000123000001" in url.replace("-", ""):
            raise RuntimeError("that document is broken")

        return form_d_xml()

    history = fetch_history("1234567", fetch=fake_fetch)

    # One survived; a partial history beats none.
    assert len(history.rounds) == 1


def test_total_raised_ignores_amendments() -> None:
    history = FundingHistory(
        cik="1",
        rounds=[
            FundingRound(
                accession="a", cik="1", filed_date="2026-01-01", amount_sold=1_000_000
            ),
            FundingRound(
                accession="b",
                cik="1",
                filed_date="2026-06-01",
                amount_sold=1_000_000,
                is_amendment=True,
            ),
        ],
    )

    # An amendment restates a round already counted, so this is 1M not 2M.
    assert history.total_raised == 1_000_000
    assert history.is_first_time is True


def test_saving_and_loading_a_history(db) -> None:
    history = FundingHistory(
        cik="1234567",
        rounds=[
            FundingRound(
                accession="a",
                cik="1234567",
                filed_date="2023-07-20",
                offering_amount=2_000_000,
                amount_sold=2_000_000,
            ),
            FundingRound(
                accession="b",
                cik="1234567",
                filed_date="2026-06-11",
                offering_amount=8_000_000,
                amount_sold=3_000_000,
            ),
        ],
    )

    assert save_history(db, history) == 2

    loaded = load_history(db, "1234567")

    assert len(loaded.rounds) == 2
    assert loaded.first_raise.filed_date == "2023-07-20"
    assert loaded.total_raised == 5_000_000


def test_a_history_loads_regardless_of_cik_padding(db) -> None:
    save_history(
        db,
        FundingHistory(
            cik="0001234567",
            rounds=[
                FundingRound(
                    accession="a", cik="0001234567", filed_date="2026-01-01"
                )
            ],
        ),
    )

    # Stored padded, asked for unpadded.
    assert len(load_history(db, "1234567").rounds) == 1


def test_resaving_updates_amounts_rather_than_duplicating(db) -> None:
    for sold in (1_000_000, 2_000_000):
        save_history(
            db,
            FundingHistory(
                cik="1",
                rounds=[
                    FundingRound(
                        accession="a",
                        cik="1",
                        filed_date="2026-01-01",
                        amount_sold=sold,
                    )
                ],
            ),
        )

    loaded = load_history(db, "1")

    assert len(loaded.rounds) == 1
    assert loaded.rounds[0].amount_sold == 2_000_000


def test_round_progress_reads_as_a_sentence() -> None:
    # The real PreventiveMD numbers.
    percent, wording = round_progress(2_000_000, 1_699_999)

    assert percent == 85
    assert "nearly closed" in wording


def test_round_progress_on_a_fully_sold_round() -> None:
    percent, wording = round_progress(1_600_000, 1_600_000)

    assert percent == 100
    assert "likely closed" in wording


def test_round_progress_on_a_freshly_opened_round() -> None:
    percent, wording = round_progress(4_000_000, 200_000)

    assert percent == 5
    assert "just opened" in wording


def test_round_progress_when_nothing_is_disclosed() -> None:
    assert round_progress(None, None) == (None, "no target disclosed")
    assert round_progress(1_000_000, None)[0] is None


def test_round_progress_with_nothing_sold() -> None:
    percent, wording = round_progress(1_000_000, 0)

    assert percent == 0
    assert "nothing sold" in wording
