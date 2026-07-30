"""Command line entry point. One JSON object or one digest on stdout."""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import closing
from pathlib import Path

from src.delivery import deliver
from src.digest import render_digest, save_digest
from src.edgar import fetch_filings
from src.pipeline import default_window, run_radar
from src.seen import connect, count_seen
from src.thesis import ThesisError, load_thesis


def command_run(args: argparse.Namespace) -> int:
    """Run the radar and print the digest."""
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

    digest = render_digest(run, thesis.name)

    print(digest)

    # Everything below goes to stderr so stdout stays exactly the digest and can
    # be piped somewhere without the commentary.
    print(
        f"index: {known_before} -> {known_after} companies known",
        file=sys.stderr,
    )

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
        sent, message = deliver(
            digest,
            subject=first_line,
            prefer_slack=args.slack,
        )
        print(message, file=sys.stderr)

        if not sent:
            return 1

    return 0


def command_status(args: argparse.Namespace) -> int:
    """Report how much the index remembers."""
    with closing(connect(Path(args.db) if args.db else None)) as connection:
        total = count_seen(connection)

    print(json.dumps({"ok": True, "companies_known": total}, indent=2))

    return 0


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
    run_parser.add_argument(
        "--limit",
        type=int,
        help="judge at most this many companies — useful for a cheap trial",
    )
    run_parser.add_argument(
        "--max-per-group",
        type=int,
        default=50,
        help="cap search results per industry group (default: 50)",
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="do not mark anything as seen, so the run can be repeated",
    )
    run_parser.add_argument("--thesis", help="path to a thesis file")
    run_parser.add_argument("--db", help="path to the seen-index")
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

    status_parser = subparsers.add_parser(
        "status",
        help="how many companies the index knows",
    )
    status_parser.add_argument("--db", help="path to the seen-index")
    status_parser.set_defaults(handler=command_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
