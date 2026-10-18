"""
The command surface, and the multi-domain run behind the daily schedule.
"""

import argparse
from contextlib import closing
from pathlib import Path

import pytest

import src.cli as cli
import src.seen as seen_module
import src.thesis as thesis_module
from src.edgar import SearchOutcome
from src.enrich import Enrichment
from src.models import Candidate, FormDFiling
from src.seen import connect
from src.thesis import Thesis, save_thesis


def a_filing(name: str, accession: str = "acc-1") -> FormDFiling:
    return FormDFiling(
        accession=accession,
        cik="1",
        company_name=name,
        filed_date="2026-08-13",
        industry_group="Other Technology",
        total_offering_amount=4_000_000,
    )


@pytest.fixture
def radar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A database and a config directory of this test's own."""
    config = tmp_path / "config"
    config.mkdir()

    monkeypatch.setattr(seen_module, "DEFAULT_DB_PATH", tmp_path / "radar.sqlite")
    monkeypatch.setattr(
        thesis_module, "DEFAULT_THESIS_PATH", config / "thesis.yaml"
    )
    monkeypatch.setattr(cli, "save_digest", lambda digest, run: tmp_path / "d.md")

    monkeypatch.setattr(
        cli,
        "fetch_filings",
        lambda *a, **k: SearchOutcome([a_filing("Acme Inc.")], [], [], ["x"]),
    )

    return config


def with_judge(monkeypatch, judge) -> None:
    """
    Inject a judge into the pipeline the CLI calls.

    run_radar takes judge and enrich as default arguments, which are bound when
    the function is defined — so patching the module attribute never reaches
    them. Wrapping the call is the seam that actually exists.
    """
    real = cli.run_radar

    def wrapped(*args, **kwargs):
        kwargs.setdefault("judge", judge)
        kwargs.setdefault("enrich", lambda filing: Enrichment())

        return real(*args, **kwargs)

    monkeypatch.setattr(cli, "run_radar", wrapped)


def arguments(**overrides) -> argparse.Namespace:
    data = {
        "start": "2026-08-12",
        "end": "2026-08-14",
        "days": 3,
        "max_per_group": 50,
        "limit": None,
        "dry_run": True,
        "thesis": None,
        "db": None,
        "all_domains": False,
        "send": False,
        "slack": False,
    }
    data.update(overrides)

    return argparse.Namespace(**data)


def a_thesis(domain: str) -> Thesis:
    return Thesis(
        domain=domain,
        name=f"{domain} companies",
        description="Anything.",
        include=["anything at all"],
        sec_industry_groups=["Other Technology"],
    )


def test_a_dry_run_still_hands_back_its_digest(radar, monkeypatch) -> None:
    """
    A rehearsal that collects nothing is not a rehearsal.

    `--all --dry-run` printed four domain headers and no digest, because the
    digest was attached after the dry-run exit rather than before it. That read
    as the radar finding nothing, rather than the code dropping it.
    """
    save_thesis(a_thesis("Healthcare"), directory=radar)

    with_judge(
        monkeypatch,
        lambda f, e, t: Candidate(filing=f, verdict="fits", reason="Because."),
    )

    args = arguments(thesis=str(next(radar.glob("*.yaml"))))

    assert cli.command_run(args) == 0
    assert getattr(args, "_digest", "")
    assert "Acme Inc." in args._digest


def test_running_all_domains_covers_every_thesis(radar, monkeypatch) -> None:
    # The schedule ran config/thesis.yaml alone, so four domains sat
    # unscheduled while looking configured.
    for domain in ("Healthcare", "Energy", "Fintech"):
        save_thesis(a_thesis(domain), directory=radar)

    seen: list[str] = []

    def judge(filing, enrichment, thesis):
        seen.append(thesis.domain)
        return Candidate(filing=filing, verdict="fits", reason="Because.")

    with_judge(monkeypatch, judge)

    assert cli.command_run(arguments(all_domains=True)) == 0
    assert sorted(seen) == ["Energy", "Fintech", "Healthcare"]


def test_one_failing_domain_does_not_lose_the_others(radar, monkeypatch) -> None:
    for domain in ("Healthcare", "Energy"):
        save_thesis(a_thesis(domain), directory=radar)

    def judge(filing, enrichment, thesis):
        if thesis.domain == "Energy":
            raise RuntimeError("the model fell over")

        return Candidate(filing=filing, verdict="fits", reason="Because.")

    with_judge(monkeypatch, judge)

    # Healthcare still reports, and the run does not fail outright.
    assert cli.command_run(arguments(all_domains=True)) == 0


def test_running_all_domains_with_no_thesis_files_is_an_error(radar) -> None:
    assert cli.command_run(arguments(all_domains=True)) == 1


def test_the_combined_message_contains_every_domain(radar, monkeypatch, capsys) -> None:
    """
    The rehearsal printed five domains individually and then a combined block
    containing only one of them. The loop ran; the collecting did not.
    """
    for domain in ("Healthcare", "Energy", "Fintech"):
        save_thesis(a_thesis(domain), directory=radar)

    with_judge(
        monkeypatch,
        lambda f, e, t: Candidate(filing=f, verdict="fits", reason="Because."),
    )

    assert cli.command_run(arguments(all_domains=True)) == 0

    printed = capsys.readouterr().out

    # Exactly once each: the combined message carries them, and the
    # per-domain runs no longer print separately. ">= 1" would have passed on
    # the individual prints alone, which is how the first version of this test
    # missed the bug it was written for.
    for domain in ("Healthcare companies", "Energy companies", "Fintech companies"):
        assert printed.count(domain) == 1, f"{domain} appears {printed.count(domain)}x"


def test_a_domain_with_its_own_recipients_is_sent_separately(radar, monkeypatch) -> None:
    """
    Parallax goes to a different inbox. It must reach that inbox alone and
    never appear in the owner's combined message.
    """
    save_thesis(a_thesis("Healthcare"), directory=radar)
    routed = a_thesis("Parallax").model_copy(update={"email_to": ["partner@fund.com"]})
    save_thesis(routed, directory=radar)

    with_judge(
        monkeypatch,
        lambda f, e, t: Candidate(filing=f, verdict="fits", reason="Because."),
    )

    combined: list[str] = []
    separate: list[tuple[str, list[str]]] = []

    monkeypatch.setattr(
        cli, "deliver",
        lambda content, subject, prefer_slack=False: (combined.append(content), (True, "sent"))[1],
    )
    monkeypatch.setattr(
        cli, "send_email",
        lambda content, subject, recipients=None: (separate.append((content, recipients)), (True, "sent"))[1],
    )

    assert cli.command_run(arguments(all_domains=True, send=True)) == 0

    assert len(combined) == 1
    assert "Healthcare companies" in combined[0]
    assert "Parallax companies" not in combined[0]

    assert len(separate) == 1
    assert "Parallax companies" in separate[0][0]
    assert separate[0][1] == ["partner@fund.com"]


def test_a_failed_separate_email_fails_the_run(radar, monkeypatch) -> None:
    # Cron reads the exit code; a domain whose email never went must not look fine.
    save_thesis(a_thesis("Healthcare"), directory=radar)
    save_thesis(
        a_thesis("Parallax").model_copy(update={"email_to": ["partner@fund.com"]}),
        directory=radar,
    )
    with_judge(
        monkeypatch,
        lambda f, e, t: Candidate(filing=f, verdict="fits", reason="Because."),
    )
    monkeypatch.setattr(cli, "deliver", lambda *a, **k: (True, "sent"))
    monkeypatch.setattr(cli, "send_email", lambda *a, **k: (False, "email failed"))

    assert cli.command_run(arguments(all_domains=True, send=True)) == 1


def test_an_address_that_is_not_an_email_is_refused() -> None:
    with pytest.raises(ValueError):
        a_thesis("Parallax").model_validate(
            {**a_thesis("Parallax").model_dump(), "email_to": ["not an address"]}
        )
