"""CLI to run the `CsvIngestionService` against `nepse_data/data`.

Usage:
    python scripts/ingest_csv.py [--csv-dir PATH] [--symbol SYMBOL] [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--dry-run]

This script is read-only by default when `--dry-run` is passed; it will parse
and validate CSVs produced by `nepse_data/scraper.py` and print a summary JSON.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.csv_ingestion import CsvIngestionService


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest NEPSE CSVs into DB (or dry-run).")
    parser.add_argument("--csv-dir", type=Path, default=None, help="Path to nepse_data/data")
    parser.add_argument("--symbol", type=str, default=None, help="Optional symbol to filter")
    parser.add_argument("--start", type=str, default=None, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", type=str, default=None, help="End date YYYY-MM-DD")
    parser.add_argument(
        "--dry-run", action="store_true", help="Parse and validate only; do not write to DB"
    )

    args = parser.parse_args()

    svc = CsvIngestionService(session=None, csv_dir=args.csv_dir)
    result = svc.run(
        symbol=args.symbol, start_date=args.start, end_date=args.end, dry_run=args.dry_run
    )

    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
