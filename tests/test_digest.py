from pathlib import Path

from src.digest import (
    format_amount,
    format_location,
    render_digest,
    save_digest,
)
from src.models import Candidate, FormDFiling
from src.pipeline import DroppedFiling, RadarRun


def candidate(
    name: str = "Acme Health, Inc.",
    verdict: str = "fits",
    reason: str = "Clinical trial software.",
    amount: int | None = 4_200_000,
    **filing_overrides,
) -> Candidate:
    data = {
        "accession": "acc-1",
        "cik": "1",
        "company_name": name,
        "filed_date": "2026-07-28",
        "industry_group": "Other Health Care",
        "city": "BOSTON",
        "state": "MA",
        "total_offering_amount": amount,
    }
    data.update(filing_overrides)

    return Candidate(
        filing=FormDFiling(**data),
        verdict=verdict,
        reason=reason,
    )


def run(**overrides) -> RadarRun:
    data = {
        "start_date": "2026-07-26",
        "end_date": "2026-07-29",
        "generated_at": "2026-07-29T08:00:00+00:00",
        "fetched": 1,
        "candidates": [candidate()],
    }
    data.update(overrides)

    return RadarRun(**data)


def test_amounts_are_rendered_the_way_an_analyst_reads_them() -> None:
    assert format_amount(4_200_000) == "$4.2M"
    assert format_amount(18_000_000) == "$18M"
    assert format_amount(645_000) == "$645k"
    assert format_amount(None) == "undisclosed"


def test_location_falls_back_gracefully() -> None:
    assert format_location(candidate()) == "Boston, MA"
    assert format_location(candidate(city=None)) == "MA"
    assert format_location(candidate(city=None, state=None)) == "location unknown"


def test_digest_header_counts_only_interesting_entries() -> None:
    content = render_digest(
        run(
            candidates=[
                candidate("Fits Co"),
                candidate("Rejected Co", verdict="no_fit", reason="A clinic."),
            ]
        ),
        "Healthcare AI",
    )

    assert "Deal Radar · 1 new · Healthcare AI · 2026-07-29" in content
    assert "Fits Co" in content
    # A rejection is counted, not listed.
    assert "Rejected Co" not in content
    assert "Judged 1 as not a fit." in content


def test_digest_says_so_when_nothing_matched() -> None:
    content = render_digest(run(candidates=[]), "Healthcare AI")

    assert "Nothing new matched the thesis." in content


def test_digest_reports_the_work_it_saved() -> None:
    content = render_digest(
        run(
            already_seen=34,
            filtered_out=[DroppedFiling(company_name="Tiny Co", reason="too small")],
        ),
        "Healthcare AI",
    )

    # This line is the point of the product.
    assert "Skipped 35 filings" in content


def test_digest_omits_the_skipped_line_when_nothing_was_skipped() -> None:
    content = render_digest(run(), "Healthcare AI")

    assert "Skipped" not in content


def test_digest_marks_a_newly_incorporated_company() -> None:
    content = render_digest(
        run(
            candidates=[
                candidate(year_of_incorporation=2026, filed_date="2026-07-28")
            ]
        ),
        "Healthcare AI",
    )

    assert "incorporated 2026" in content


def test_digest_shows_verdict_marks() -> None:
    content = render_digest(
        run(
            candidates=[
                candidate("Sure Thing", verdict="fits"),
                candidate("Unclear Co", verdict="maybe", reason="Thin evidence."),
            ]
        ),
        "Healthcare AI",
    )

    assert "✓ Clinical trial software." in content
    assert "~ Thin evidence." in content


def test_digest_includes_a_website_when_one_was_found() -> None:
    entry = candidate()
    entry.website = "https://acmehealth.com"

    content = render_digest(run(candidates=[entry]), "Healthcare AI")

    assert "https://acmehealth.com" in content


def test_digest_lists_problems_but_caps_them() -> None:
    content = render_digest(
        run(problems=[f"problem {n}" for n in range(9)]),
        "Healthcare AI",
    )

    assert "9 problems:" in content
    assert "problem 0" in content
    # Capped so a bad day does not produce an unreadable message.
    assert "problem 8" not in content


def test_digest_ends_with_exactly_one_newline() -> None:
    content = render_digest(run(), "Healthcare AI")

    assert content.endswith("\n")
    assert not content.endswith("\n\n")


def test_save_digest_names_the_file_by_date(tmp_path: Path) -> None:
    path = save_digest("# digest", run(), output_directory=tmp_path)

    assert path.name == "2026-07-29.md"
    assert path.read_text(encoding="utf-8") == "# digest"


def test_save_digest_overwrites_a_rerun_of_the_same_day(tmp_path: Path) -> None:
    save_digest("first", run(), output_directory=tmp_path)
    path = save_digest("second", run(), output_directory=tmp_path)

    assert path.read_text(encoding="utf-8") == "second"
    assert len(list(tmp_path.glob("*.md"))) == 1


def test_save_digest_leaves_no_temporary_file(tmp_path: Path) -> None:
    save_digest("x", run(), output_directory=tmp_path)

    assert not list(tmp_path.glob("*.tmp"))
