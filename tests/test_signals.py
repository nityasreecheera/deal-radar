"""
What the filings say is true of a company, and what they say is not.

Two rules underneath all of it. Nothing here predicts an outcome — there are no
outcomes on record to learn from. And nothing is totalled, because any weighting
of "raised before" against "ten investors" is invented here rather than read off
a filing.
"""

from src.candidates import StoredCandidate
from src.funding import FundingHistory, FundingRound
from src.signals import assess, days_between


def company(**overrides) -> StoredCandidate:
    data = {
        "accession": "acc-1",
        "canonical_name": "acme",
        "company_name": "Acme Inc.",
        "verdict": "fits",
        "reason": "Because.",
        "filed_date": "2026-08-20",
        "judged_at": "2026-08-20T00:00:00+00:00",
    }
    data.update(overrides)

    return StoredCandidate(**data)


def history(*rounds: tuple[str, int, bool]) -> FundingHistory:
    return FundingHistory(
        cik="1",
        rounds=[
            FundingRound(
                accession=f"a-{index}",
                cik="1",
                filed_date=filed,
                offering_amount=amount,
                is_amendment=amendment,
            )
            for index, (filed, amount, amendment) in enumerate(rounds)
        ],
    )


def fired(assessment) -> set[str]:
    return {s.name for s in assessment.fired}


def test_a_company_with_nothing_on_file_says_nothing() -> None:
    """
    A filing with no amounts, no investors, no incorporation year and no
    history supports no statements at all — so none are made.

    An earlier version always produced at least "findable online", which fired
    on three quarters of everything and told nobody anything. A list of
    failures about a company nobody could look up is worse than an empty panel,
    which the interface hides.
    """
    result = assess(company(), today="2026-08-20")

    assert result.signals == []
    assert "Nothing checkable" in result.describe()


def test_a_sold_out_round_counts_as_demand() -> None:
    result = assess(
        company(offering_amount=2_000_000, amount_sold=2_000_000),
        today="2026-08-20",
    )

    assert "Round nearly or fully sold" in fired(result)


def test_a_barely_started_round_does_not() -> None:
    result = assess(
        company(offering_amount=2_000_000, amount_sold=50_000),
        today="2026-08-20",
    )

    assert "Round nearly or fully sold" not in fired(result)
    # Still counted in the denominator: we checked and the answer was no.
    assert any(s.name == "Round nearly or fully sold" for s in result.signals)


def test_raising_more_than_last_time_leads_the_list() -> None:
    result = assess(
        company(),
        history=history(("2024-01-10", 2_000_000, False), ("2026-08-20", 9_000_000, False)),
        today="2026-08-20",
    )

    growth = next(s for s in result.signals if s.name == "Raising more than last time")

    assert growth.fired
    # Weight orders the list rather than adding to a total, so the signal that
    # carries the most sits first.
    assert result.signals[0].name == "Raising more than last time"


def test_a_smaller_round_than_last_time_does_not_fire() -> None:
    result = assess(
        company(),
        history=history(("2024-01-10", 9_000_000, False), ("2026-08-20", 2_000_000, False)),
        today="2026-08-20",
    )

    assert "Raising more than last time" not in fired(result)


def test_a_company_with_no_history_is_asked_fewer_questions() -> None:
    # Not penalised for a history nobody has: the cross-filing signals are
    # absent from the list entirely rather than listed as failures.
    without = assess(company(), today="2026-08-20")
    with_one = assess(
        company(), history=history(("2026-08-20", 2_000_000, False)), today="2026-08-20"
    )

    assert len(with_one.signals) > len(without.signals)
    assert "Has raised before" not in {s.name for s in without.signals}


def test_an_oversubscribed_round_is_recognised() -> None:
    result = assess(
        company(),
        history=history(
            ("2026-01-21", 88_500_025, False), ("2026-06-10", 91_454_999, True)
        ),
        today="2026-08-20",
    )

    assert "Round grew after filing" in fired(result)


def test_a_company_with_everything_has_nothing_in_the_second_list() -> None:
    everything = assess(
        company(
            offering_amount=2_000_000,
            amount_sold=2_000_000,
            investor_count=14,
            minimum_investment=250_000,
            incorporated=2026,
            first_sale_date="2026-08-10",
            website="https://acme.com",
        ),
        history=history(("2025-06-01", 1_000_000, False), ("2026-08-20", 2_000_000, False)),
        today="2026-08-20",
    )

    assert everything.missing == []
    assert len(everything.fired) == len(everything.signals)


def test_every_signal_explains_itself() -> None:
    result = assess(
        company(offering_amount=1_000_000, amount_sold=900_000),
        today="2026-08-20",
    )

    # A line nobody can check is an opinion wearing evidence's clothes.
    assert all(s.means for s in result.signals)
    assert all(s.detail for s in result.signals)


def test_a_malformed_date_does_not_crash_the_score() -> None:
    assert days_between("not a date", "2026-01-01") is None
    assert assess(company(first_sale_date="nonsense"), today="2026-08-20")


def test_the_description_never_claims_a_prediction() -> None:
    text = assess(
        company(offering_amount=1_000, amount_sold=1_000), today="2026-08-20"
    ).describe()

    assert "true" in text
    for forbidden in ("likely", "probability", "chance", "score", "will succeed"):
        assert forbidden not in text.lower()


def test_nothing_is_totalled() -> None:
    # Any weighting of "raised before" against "ten investors" is invented here
    # rather than read off a filing. Presenting one as a total would make an
    # invisible judgement look like a measurement.
    result = assess(company(offering_amount=1_000, amount_sold=1_000))

    assert not hasattr(result, "points")
    assert not hasattr(result, "out_of_ten")


def test_growth_is_measured_against_the_amended_amount() -> None:
    """
    Cornelis Networks opened at $25m and amended to $245m, against a previous
    round of $45m. Comparing the opening figure said "raising less than last
    time" about a round five times the size — the same mistake as reporting
    Proxima Bio's $88.5m and ignoring the $91.5m it became.
    """
    result = assess(
        company(),
        history=history(
            ("2025-11-01", 45_000_000, False),
            ("2026-08-01", 25_000_000, False),
            ("2026-08-20", 245_000_000, True),
        ),
        today="2026-08-20",
    )

    growth = next(s for s in result.signals if s.name == "Raising more than last time")

    assert growth.fired
    assert "245,000,000" in growth.detail
    assert "after amendment" in growth.detail


def test_a_genuine_down_round_still_reads_as_one() -> None:
    result = assess(
        company(),
        history=history(
            ("2025-01-01", 40_000_000, False), ("2026-08-01", 12_000_000, False)
        ),
        today="2026-08-20",
    )

    assert "Raising more than last time" not in fired(result)
