"""Command line jobs: python -m bbdfi.cli <command>"""

import argparse
import json
from datetime import date

from bbdfi import jobs
from bbdfi.config import get_settings
from bbdfi.db import SessionLocal, init_db
from bbdfi.engine.runner import run_pending


def main() -> None:
    parser = argparse.ArgumentParser(prog="bbdfi")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db", help="Create tables (and enable RLS on Supabase)")
    seed = commands.add_parser("seed-sample", help="Load deterministic sample prices for local development")
    seed.add_argument("--days", type=int, default=180)
    ingest = commands.add_parser("ingest", help="Load one day's NSE Bhavcopy")
    ingest.add_argument("--date", type=date.fromisoformat, default=date.today())
    fill = commands.add_parser("backfill", help="Load the last N calendar days of NSE Bhavcopy")
    fill.add_argument("--days", type=int, default=180)
    commands.add_parser("run-engine", help="Run strategies and snapshot equity for unprocessed days")
    daily = commands.add_parser("daily", help="ingest + run-engine (schedule after 7 PM IST on weekdays)")
    daily.add_argument("--date", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()

    settings = get_settings()
    init_db()
    with SessionLocal() as session:
        if args.command == "init-db":
            print("Tables ready.")
        elif args.command == "seed-sample":
            print(f"Loaded {jobs.seed_sample(session, args.days)} sample bars.")
        elif args.command == "ingest":
            print(f"Loaded {jobs.ingest_day(session, args.date, settings.universe)} bars for {args.date}.")
        elif args.command == "backfill":
            print(json.dumps(jobs.backfill(session, args.days, settings.universe), indent=2))
        elif args.command in ("run-engine", "daily"):
            if args.command == "daily":
                print(f"Loaded {jobs.ingest_day(session, args.date, settings.universe)} bars for {args.date}.")
            for summary in run_pending(session):
                print(f"{summary.day}: {summary.strategies_run} strategies, {summary.filled} filled, "
                      f"{summary.rejected} rejected, {summary.snapshots} snapshots {summary.errors or ''}")


if __name__ == "__main__":
    main()
