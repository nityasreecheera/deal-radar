"""Command line entry point. One JSON object or one digest on stdout."""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import closing
from pathlib import Path

from src.candidates import (
    count_by_verdict,
    find_by_company,
    list_candidates,
)
from src.delivery import deliver
from src.candidates import describe_category, quarter_start
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

        # How each company sits against the ones like it. Worked out here
        # because it needs the database, and while the connection is still open.
        contexts = {
            candidate.filing.accession: describe_category(
                connection, candidate, since=quarter_start(end), theme=thesis.name
            )
            for candidate in run.interesting
        }

    digest = render_digest(run, thesis.name, contexts)

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
