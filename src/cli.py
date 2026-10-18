"""Command line entry point. One JSON object or one digest on stdout."""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import closing
from pathlib import Path

from src.archive import archive_range
from src.candidates import (
    count_by_verdict,
    find_by_company,
    list_candidates,
)
from src.delivery import deliver, send_email
from src.candidates import (
    category_lines,
    describe_rejection_clusters,
    quarter_start,
)
from src.digest import render_digest, save_digest
from src.momentum import detect, mark_sent, render_section, unsent
from src.edgar import fetch_filings
from src.pipeline import default_window, run_radar
from src.seen import connect, count_seen
from src.thesis import Thesis, ThesisError, load_all_theses, load_thesis


def command_run(args: argparse.Namespace) -> int:
    """
    Run the radar and print the digest.

    With --all, every thesis on disk runs and the digests are joined into one
    message. Five separate emails each morning, four of them usually saying
    nothing happened, is how a daily habit stops being one.
    """
    if getattr(args, "all_domains", False):
        return run_every_domain(args)

    preloaded = getattr(args, "_thesis_object", None)

    if preloaded is not None:
        thesis = preloaded
    else:
        try:
            thesis = load_thesis(Path(args.thesis) if args.thesis else None)
        except ThesisError as exc:
            print(f"error: {exc}", file=sys.stderr)

            return 1

    if args.start and args.end:
        start, end = args.start, args.end
    else:
        start, end = default_window(days=args.days)

    def fetch(start_date: str, end_date: str):
        return fetch_filings(
            start_date,
            end_date,
            industry_groups=thesis.sec_industry_groups,
            max_per_group=args.max_per_group,
        )

    with closing(connect(Path(args.db) if args.db else None)) as connection:
        known_before = count_seen(connection)

        run = run_radar(
            connection,
            thesis,
            start,
            end,
            fetch_filings=fetch,
            mark=not args.dry_run,
            limit=args.limit,
        )

        known_after = count_seen(connection)

        # How each company sits against the ones like it. Worked out here
        # because it needs the database, and while the connection is still open.
        # domain, not name. Judgements are stored under the short label;
        # `name` is the human description, and filtering on it matches nothing
        # at all — silently, which is the problem.
        contexts = category_lines(
            connection,
            run.interesting,
            since=quarter_start(end),
            theme=thesis.domain,
        )

        clusters = describe_rejection_clusters(
            connection, since=quarter_start(end), theme=thesis.domain
        )

        # Companies this domain already judged that filed again since. Sent once:
        # marked only after an email actually carrying them goes out.
        pending = unsent(connection, thesis.domain)

    digest = render_digest(run, thesis.name, contexts, clusters)

    section = render_section(pending)

    if section:
        digest = digest.rstrip() + "\n\n" + section + "\n"

    args._signals = (thesis.domain, [signal.accession for signal in pending])

    # Silent when another run is collecting this one — otherwise stdout carries
    # every domain twice, once alone and once inside the combined message.
    if not getattr(args, "_collected", False):
        print(digest)

    # Everything below goes to stderr so stdout stays exactly the digest and can
    # be piped somewhere without the commentary.
    print(
        f"index: {known_before} -> {known_after} companies known",
        file=sys.stderr,
    )

    # Handed back before the dry-run exit, not after. A rehearsal that collects
    # nothing is not a rehearsal — `--all --dry-run` printed four domain headers
    # and no digest, which looked like the run finding nothing rather than the
    # code dropping it on the floor.
    args._digest = digest

    if args.dry_run:
        print(
            "dry run — nothing was marked as seen, so this can be repeated",
            file=sys.stderr,
        )

        return 0

    path = save_digest(digest, run)
    print(f"saved {path}", file=sys.stderr)

    if args.send:
        first_line = digest.splitlines()[0] if digest else "Deal Radar"
        sent, message = deliver_for(thesis, digest, first_line, args.slack)
        print(message, file=sys.stderr)

        if not sent:
            return 1

        record_signals_sent(args, [args._signals])

    return 0


def record_signals_sent(args: argparse.Namespace, batches: list[tuple[str, list[str]]]) -> None:
    """Remember which signals went out, so tomorrow's email does not repeat them."""
    if getattr(args, "dry_run", False):
        return

    with closing(connect(Path(args.db) if args.db else None)) as connection:
        for theme, accessions in batches:
            if accessions:
                mark_sent(connection, theme, accessions)


def run_every_domain(args: argparse.Namespace) -> int:
    """
    Run each thesis in turn and send one message covering all of them.

    A domain that found nothing still contributes its counts, because "nothing
    new in Energy" is information — it is only noise when it arrives as its own
    email. The sections are ordered by what each found, so the mornings when
    something happened read as if they did.
    """
    theses = load_all_theses()

    if not theses:
        print("error: no thesis files in config/", file=sys.stderr)

        return 1

    sections: list[tuple[int, str]] = []
    # Domains with their own recipients get their own email and stay out of the
    # combined one, so what goes to someone else never lands in the owner's inbox.
    routed: list[tuple[Thesis, str, tuple[str, list[str]]]] = []
    combined_signals: list[tuple[str, list[str]]] = []
    failed = 0

    for thesis in theses:
        print(f"— {thesis.domain} —", file=sys.stderr)

        one = argparse.Namespace(**vars(args))
        one.all_domains = False
        one.thesis = None
        one.send = False
        one._thesis_object = thesis
        one._collected = True

        try:
            code = command_run(one)
        except Exception as exc:  # noqa: BLE001 - one domain must not stop the rest
            print(f"  {thesis.domain} failed: {exc}", file=sys.stderr)
            failed += 1
            continue

        if code != 0:
            failed += 1
            continue

        digest = getattr(one, "_digest", "")
        signals = getattr(one, "_signals", (thesis.domain, []))

        if digest and thesis.email_to:
            routed.append((thesis, digest, signals))
        elif digest:
            combined_signals.append(signals)
            # Ordered by what was found, so a morning with something in it does
            # not open with four quiet domains.
            found = digest.count("\n1. ")
            sections.append((found, digest))

    undelivered = 0

    for thesis, digest, _ in routed:
        print(f"— {thesis.domain}: its own email, not in the combined one —", file=sys.stderr)
        print(digest, file=sys.stderr)

    if args.send:
        for thesis, digest, signals in routed:
            subject = digest.splitlines()[0] if digest else f"Deal Radar · {thesis.domain}"
            sent, message = deliver_for(thesis, digest, subject, args.slack)
            print(f"{thesis.domain}: {message}", file=sys.stderr)

            if sent:
                record_signals_sent(args, [signals])
            else:
                undelivered += 1

    if not sections:
        return 1 if undelivered or not routed else 0

    sections.sort(key=lambda item: -item[0])
    combined = "\n\n".join(text.rstrip() for _, text in sections) + "\n"

    print(combined)

    if args.send:
        total = sum(count for count, _ in sections)
        subject = f"Deal Radar · {total} new across {len(sections)} domains"

        sent, message = deliver(combined, subject=subject, prefer_slack=args.slack)
        print(message, file=sys.stderr)

        if not sent:
            return 1

        record_signals_sent(args, combined_signals)

    if undelivered:
        return 1

    return 1 if failed and not sections else 0


def deliver_for(thesis: Thesis, digest: str, subject: str, prefer_slack: bool) -> tuple[bool, str]:
    """
    Send one domain's digest to wherever that domain says it goes.

    A domain with its own recipients goes by email only. Falling back to the
    owner's Slack would put it in front of someone it was routed away from.
    """
    if thesis.email_to:
        return send_email(digest, subject, recipients=thesis.email_to)

    return deliver(digest, subject=subject, prefer_slack=prefer_slack)


def command_status(args: argparse.Namespace) -> int:
    """Report how much the index remembers."""
    with closing(connect(Path(args.db) if args.db else None)) as connection:
        total = count_seen(connection)
        verdicts = count_by_verdict(connection)

    print(
        json.dumps(
            {
                "ok": True,
                "companies_known": total,
                "judgements": verdicts,
            },
            indent=2,
        )
    )

    return 0


def command_candidates(args: argparse.Namespace) -> int:
    """List past judgements — what was decided, and why."""
    with closing(connect(Path(args.db) if args.db else None)) as connection:
        if args.company:
            found = find_by_company(connection, args.company)
        else:
            found = list_candidates(
                connection,
                verdicts=args.verdict,
                since=args.since,
                limit=args.limit,
            )

    if args.json:
        print(
            json.dumps(
                {
                    "ok": True,
                    "count": len(found),
                    "candidates": [c.model_dump(mode="json") for c in found],
                },
                indent=2,
            )
        )

        return 0

    if not found:
        print("Nothing recorded matches that.")

        return 0

    mark = {"fits": "✓", "maybe": "~", "no_fit": "✗"}

    for item in found:
        amount = (
            f"${item.offering_amount:,}"
            if item.offering_amount is not None
            else "undisclosed"
        )

        print(f"{mark[item.verdict]} {item.company_name} · {amount} · {item.filed_date}")
        print(f"   {item.reason}")

        if item.website:
            print(f"   {item.website}")

        print()

    return 0


def command_set_domain(args: argparse.Namespace) -> int:
    """
    Label judgements that have no domain recorded.

    Rows judged before the column existed have none. They were all judged
    against the single thesis in use at the time, so recording that is accurate
    rather than invented — which is why this only fills blanks by default.
    """
    with closing(connect(Path(args.db) if args.db else None)) as connection:
        clause = "" if args.overwrite else " WHERE theme IS NULL OR theme = ''"
        cursor = connection.execute(
            f"UPDATE candidate SET theme = ?{clause}",
            (args.domain,),
        )
        connection.commit()

        print(
            json.dumps(
                {"ok": True, "domain": args.domain, "updated": cursor.rowcount},
                indent=2,
            )
        )

    return 0


def command_archive(args: argparse.Namespace) -> int:
    """
    Store every Form D filed in a range, in every industry group.

    Nothing is looked up or judged, so this costs nothing but time: one search
    page per ten filings and one download per filing, at EDGAR's polite rate.
    Prints one line per day and exits non-zero if any day was not read in full,
    so a scheduled run that half-failed is visible in the log.
    """
    if args.start and args.end:
        start, end = args.start, args.end
    else:
        start, end = default_window(days=args.days)

    with closing(connect(Path(args.db) if args.db else None)) as connection:
        run = archive_range(connection, start, end)

        # Later filings from companies already judged, compared with what they
        # filed before. Free, and it has to follow the archive it reads from.
        signals = detect(connection, start)

    for day in run.days:
        state = "complete" if day.complete else f"INCOMPLETE ({len(day.problems)} problems)"
        print(f"{day.day}  {day.filings:4} filings  {state}")

        for problem in day.problems[:5]:
            print(f"    {problem}")

    print(f"{run.filings} filings stored across {len(run.days)} days")
    strong = sum(1 for signal in signals if signal.strong)
    print(f"{len(signals)} new signals from companies already judged ({strong} strong)")

    return 1 if run.incomplete else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m src.cli",
        description="Deal Radar — newly visible companies you have not seen.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="run the radar")
    run_parser.add_argument("--start", help="start date, YYYY-MM-DD")
    run_parser.add_argument("--end", help="end date, YYYY-MM-DD")
    run_parser.add_argument(
        "--days",
        type=int,
        default=3,
        help="window size when no dates are given (default: 3, to cover weekends)",
    )
    # The limit that matters for cost is on judging, not fetching. Fetching from
    # EDGAR is free, and capping it at 50 a group silently dropped real filings
    # on any busy day — 13 of 63 in Other Technology over one weekend.
    run_parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="judge at most this many companies per domain (default: 200); "
        "anything over is reported, not dropped",
    )
    run_parser.add_argument(
        "--max-per-group",
        type=int,
        default=500,
        help="cap search results per industry group (default: 500)",
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="do not mark anything as seen, so the run can be repeated",
    )
    run_parser.add_argument("--thesis", help="path to a thesis file")
    run_parser.add_argument("--db", help="path to the seen-index")
    run_parser.add_argument(
        "--all",
        dest="all_domains",
        action="store_true",
        help="run every thesis in config/ and send one message covering all",
    )
    run_parser.add_argument(
        "--send",
        action="store_true",
        help="deliver the digest by email, falling back to Slack",
    )
    run_parser.add_argument(
        "--slack",
        action="store_true",
        help="deliver via Slack instead of trying email first",
    )
    run_parser.set_defaults(handler=command_run)

    archive_parser = subparsers.add_parser(
        "archive",
        help="store every Form D in a range, without judging any of them",
    )
    archive_parser.add_argument("--start", help="start date, YYYY-MM-DD")
    archive_parser.add_argument("--end", help="end date, YYYY-MM-DD")
    archive_parser.add_argument(
        "--days",
        type=int,
        default=3,
        help="window size when no dates are given (default: 3, to cover weekends)",
    )
    archive_parser.add_argument("--db", help="path to the seen-index")
    archive_parser.set_defaults(handler=command_archive)

    status_parser = subparsers.add_parser(
        "status",
        help="how many companies the index knows",
    )
    status_parser.add_argument("--db", help="path to the seen-index")
    status_parser.set_defaults(handler=command_status)

    candidates_parser = subparsers.add_parser(
        "candidates",
        help="what was decided about past companies, and why",
    )
    candidates_parser.add_argument(
        "--verdict",
        action="append",
        choices=["fits", "maybe", "no_fit"],
        help="only this verdict (repeatable)",
    )
    candidates_parser.add_argument(
        "--company",
        help="every judgement about one company, by name",
    )
    candidates_parser.add_argument(
        "--since",
        help="only filings on or after this date, YYYY-MM-DD",
    )
    candidates_parser.add_argument("--limit", type=int)
    candidates_parser.add_argument(
        "--json",
        action="store_true",
        help="machine-readable output",
    )
    candidates_parser.add_argument("--db", help="path to the seen-index")
    candidates_parser.set_defaults(handler=command_candidates)

    domain_parser = subparsers.add_parser(
        "set-domain",
        help="label judgements that have no domain recorded",
    )
    domain_parser.add_argument("--domain", required=True)
    domain_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="relabel everything, not only the blanks",
    )
    domain_parser.add_argument("--db", help="path to the seen-index")
    domain_parser.set_defaults(handler=command_set_domain)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
