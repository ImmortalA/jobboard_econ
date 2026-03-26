from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import DbPaths, connect, init_db, upsert_jobs  # noqa: E402
from app.linkedin_import import scrape_linkedin_jobs, linkedin_csv_rows_to_db_rows  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch and persist jobs from LinkedIn (via jobsparser)")
    ap.add_argument("--root", default=".", help="Project root (default: .)")
    ap.add_argument("--scrape", action="store_true", help="Run jobsparser to scrape fresh LinkedIn CSVs")
    ap.set_defaults(scrape=False)
    ap.add_argument("--hours-old", type=int, default=720, help="Only keep jobs posted within this many hours (~30d default)")
    ap.add_argument("--results-wanted", type=int, default=200, help="jobsparser --results-wanted")
    ap.add_argument("--output-dir", default="data/linkedin", help="Directory where jobsparser writes CSVs")
    ap.add_argument(
        "--scrape-timeout-seconds",
        type=int,
        default=120,
        help="Hard timeout for the LinkedIn scraping step (seconds).",
    )
    args = ap.parse_args()

    root = DbPaths(root=dt_path(args.root))
    conn = connect(root.db_path)
    init_db(conn)

    now = dt.datetime.now(dt.timezone.utc)

    csv_paths = []
    if args.scrape:
        csv_paths = scrape_linkedin_jobs(
            output_dir=Path(args.output_dir),
            hours_old=args.hours_old,
            results_wanted=args.results_wanted,
            timeout_seconds=args.scrape_timeout_seconds,
        )
    else:
        out_dir = Path(args.output_dir)
        cutoff = now - dt.timedelta(days=2)
        csv_paths = []
        if out_dir.exists():
            for p in out_dir.glob("*.csv"):
                try:
                    mtime = dt.datetime.fromtimestamp(p.stat().st_mtime, tz=dt.timezone.utc)
                except Exception:
                    continue
                if mtime >= cutoff:
                    csv_paths.append(p)

    rows = linkedin_csv_rows_to_db_rows(csv_paths, now=now)
    upsert_jobs(conn, rows)

    print(f"Imported {len(rows)} job rows from {len(csv_paths)} CSV files.")
    return 0


def dt_path(p: str):
    return Path(p).resolve()


if __name__ == "__main__":
    raise SystemExit(main())

