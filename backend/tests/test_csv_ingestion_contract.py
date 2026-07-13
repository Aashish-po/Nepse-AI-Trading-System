from __future__ import annotations

import csv
from pathlib import Path

from app.services.csv_ingestion import CsvIngestionService


def _write_csv(path: Path, headers: list[str], rows: list[list[str]]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf8") as fh:
        writer = csv.writer(fh)
        writer.writerow(headers)
        writer.writerows(rows)


def test_csv_ingestion_parses_both_sources_and_respects_schema(tmp_path: Path) -> None:
    # Create sample sharesansar file
    data_dir = tmp_path / "nepse_data" / "data"
    ss_path = data_dir / "sharesansar" / "2026-07-01.csv"
    _write_csv(
        ss_path,
        ["Symbol", "Open", "High", "Low", "Close", "Vol"],
        [["ABC", "100", "110", "95", "105", "1000"]],
    )

    # Create sample merolagani file
    mg_path = data_dir / "merolagani" / "2026-07-01.csv"
    _write_csv(
        mg_path,
        ["Symbol", "Rate", "Quantity", "#"],
        [["XYZ", "50", "200", "1"]],
    )

    svc = CsvIngestionService(session=None, csv_dir=data_dir)
    res = svc.run(dry_run=True)

    assert res["files_processed"] == 2
    assert res["schema_errors"] == 0
    assert res["fetched"] == 2


def test_csv_ingestion_schema_mismatch_counts_schema_errors(tmp_path: Path) -> None:
    data_dir = tmp_path / "nepse_data" / "data"
    # malformed sharesansar missing required cols
    ss_path = data_dir / "sharesansar" / "2026-07-02.csv"
    _write_csv(ss_path, ["Symbol", "Close"], [["ABC", "105"]])

    # valid merolagani
    mg_path = data_dir / "merolagani" / "2026-07-02.csv"
    _write_csv(
        mg_path,
        ["Symbol", "Rate", "Quantity"],
        [["XYZ", "52", "300"]],
    )

    svc = CsvIngestionService(session=None, csv_dir=data_dir)
    res = svc.run(dry_run=True)

    assert res["files_processed"] == 1
    assert res["schema_errors"] == 1
    assert res["fetched"] == 1
