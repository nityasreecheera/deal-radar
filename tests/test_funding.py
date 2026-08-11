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
    describe_minimum,
    round_age,
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


def test_an_upward_amendment_is_reported() -> None:
    # Proxima Bio opened at $88.5m and amended to $91.5m. Reporting only the
    # original understates the round and hides that it filled.
    history = FundingHistory(
        cik="1",
        rounds=[
            FundingRound(
                accession="a",
                cik="1",
                filed_date="2026-01-21",
                offering_amount=88_500_025,
                amount_sold=86_264_999,
            ),
            FundingRound(
                accession="b",
                cik="1",
                filed_date="2026-06-10",
                offering_amount=91_454_999,
                amount_sold=91_454_999,
                is_amendment=True,
            ),
        ],
    )

    assert history.amended_upward == (88_500_025, 91_454_999)

    described = history.describe()

    assert "$88,500,025" in described
    assert "amended up to $91,454,999" in described
    # Still one round, not two.
    assert history.is_first_time is True


def test_an_amendment_that_does_not_raise_the_amount_is_not_reported() -> None:
    history = FundingHistory(
        cik="1",
        rounds=[
            FundingRound(
                accession="a", cik="1", filed_date="2026-01-01",
                offering_amount=5_000_000,
            ),
            FundingRound(
                accession="b", cik="1", filed_date="2026-06-01",
                offering_amount=5_000_000, is_amendment=True,
            ),
        ],
    )

    assert history.amended_upward is None
    assert "amended" not in history.describe()


def test_no_amendment_means_nothing_to_report() -> None:
    history = FundingHistory(
        cik="1",
        rounds=[
            FundingRound(
                accession="a", cik="1", filed_date="2026-01-01",
                offering_amount=5_000_000,
            )
        ],
    )

    assert history.amended_upward is None
    assert history.describe() == "First raise on record, opened 2026-01-01."


def test_a_round_filed_the_week_it_opened_reads_as_fresh() -> None:
    # Kairo Health Labs: first sale 3 August, filed 10 August.
    days, phrase = round_age("2026-08-03", "2026-08-10")

    assert days == 7
    assert "just opened" in phrase


def test_a_year_old_round_is_not_a_new_one() -> None:
    # The whole point. Synthesis Health filed in August 2026 having taken its
    # first money in July 2025, and arrived looking exactly as new as Kairo.
    days, phrase = round_age("2025-07-25", "2026-08-05")

    assert days == 376
    assert "over a year" in phrase


def test_round_age_in_weeks_and_months() -> None:
    assert "weeks" in round_age("2026-07-23", "2026-08-07")[1]
    assert "months" in round_age("2026-02-01", "2026-08-01")[1]


def test_an_undisclosed_first_sale_says_so_rather_than_guessing() -> None:
    days, phrase = round_age(None, "2026-08-10")

    assert days is None
    assert "not disclosed" in phrase


def test_a_first_sale_after_the_filing_is_not_negative_days() -> None:
    # A round that has not opened yet. Reporting "-20 days open" is nonsense.
    days, phrase = round_age("2026-09-01", "2026-08-10")

    assert days is None
    assert "had not opened" in phrase


def test_an_unparseable_date_does_not_crash_a_run() -> None:
    assert round_age("not a date", "2026-08-10")[0] is None


def test_the_minimum_cheque_says_who_the_round_is_for() -> None:
    assert "friends and family" in describe_minimum(5_000)
    assert "angel" in describe_minimum(50_000)
    assert "institutional" in describe_minimum(250_000)


def test_no_stated_minimum_is_not_a_minimum_of_zero() -> None:
    # Rendering 0 as "$0 minimum" reads as a number the company chose.
    assert describe_minimum(0) is None
    assert describe_minimum(None) is None


def test_a_token_minimum_reads_as_a_closed_allocation() -> None:
    # Proxima Bio filed a $1 minimum on a $91m round.
    assert "allocation likely settled" in describe_minimum(1)
