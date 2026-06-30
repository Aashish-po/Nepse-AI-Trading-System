from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from app.models.price import Price
from app.models.stock import Stock
from app.services.csv_ingestion import CsvIngestionService
from sqlalchemy.orm import Session

SS_HEADER = "date,Symbol,Open,High,Low,Close,Vol"
ML_HEADER = "date,#,Symbol,Quantity,Rate"


def _write(csv_dir: Path, source: str, day: str, lines: list[str]) -> None:
    d = csv_dir / source
    d.mkdir(parents=True, exist_ok=True)
    header = SS_HEADER if source == "sharesansar" else ML_HEADER
    (d / f"{day}.csv").write_text("\n".join([header, *lines]) + "\n")


def _seed(db: Session, *symbols: str) -> None:
    db.add_all(Stock(symbol=s, is_active=True) for s in symbols)
    db.commit()


def _svc(db: Session, csv_dir: Path) -> CsvIngestionService:
    return CsvIngestionService(session=db, csv_dir=csv_dir)


def test_inserts_data(db_session: Session, tmp_path: Path) -> None:
    _seed(db_session, "NABIL")
    _write(tmp_path, "sharesansar", "2026-06-16", ["2026-06-16,NABIL,500,510,495,505,1000"])

    result = _svc(db_session, tmp_path).run()

    assert result["inserted"] == 1
    assert result["rejected"] == 0
    price = db_session.scalar(sa.select(Price))
    assert price is not None
    assert float(price.close) == 505.0


def test_idempotent(db_session: Session, tmp_path: Path) -> None:
    _seed(db_session, "NABIL")
    _write(tmp_path, "sharesansar", "2026-06-16", ['2026-06-16,NABIL,"1,200",1210,1195,1205,500'])

    first = _svc(db_session, tmp_path).run()
    second = _svc(db_session, tmp_path).run()

    assert first["inserted"] == 1
    assert second["inserted"] == 0
    assert second["updated"] == 1
    assert db_session.scalar(sa.select(sa.func.count()).select_from(Price)) == 1


def test_ohlcv_validation_rejects_bad_row(db_session: Session, tmp_path: Path) -> None:
    _seed(db_session, "NABIL")
    # open > high
    _write(tmp_path, "sharesansar", "2026-06-16", ["2026-06-16,NABIL,600,510,495,505,1000"])

    result = _svc(db_session, tmp_path).run()

    assert result["inserted"] == 0
    assert result["rejected"] == 1


def test_source_merge_prefers_sharesansar(db_session: Session, tmp_path: Path) -> None:
    _seed(db_session, "NABIL")
    _write(tmp_path, "sharesansar", "2026-06-16", ["2026-06-16,NABIL,500,510,495,505,1000"])
    # Merolagani floor sheet: two ticks for the same day.
    _write(
        tmp_path,
        "merolagani",
        "2026-06-16",
        ["2026-06-16,1,NABIL,300,400.00", "2026-06-16,2,NABIL,200,402.00"],
    )

    result = _svc(db_session, tmp_path).run()

    assert result["inserted"] == 1  # merged to one row
    price = db_session.scalar(sa.select(Price))
    assert price is not None
    assert float(price.close) == 505.0  # ShareSansar won the tiebreak


def test_merolagani_aggregates_to_ohlcv(db_session: Session, tmp_path: Path) -> None:
    _seed(db_session, "BEDC")
    _write(
        tmp_path,
        "merolagani",
        "2026-06-16",
        [
            "2026-06-16,1,BEDC,300,377.00",
            "2026-06-16,2,BEDC,20,377.70",
            "2026-06-16,3,BEDC,28,376.00",
        ],
    )

    _svc(db_session, tmp_path).run()

    price = db_session.scalar(sa.select(Price))
    assert price is not None
    assert float(price.open) == 377.00  # first by '#'
    assert float(price.high) == 377.70
    assert float(price.low) == 376.00
    assert float(price.close) == 376.00  # last by '#'
    assert price.volume == 348


def test_skips_holiday_file(db_session: Session, tmp_path: Path) -> None:
    _seed(db_session, "NABIL")
    _write(tmp_path, "sharesansar", "2026-06-16", [])  # header only
    _write(tmp_path, "merolagani", "2026-06-15", ["2026-06-15,1,NABIL,10,500.00"])

    result = _svc(db_session, tmp_path).run()

    assert result["holiday_skips"] == 1
    assert result["inserted"] == 1  # the real merolagani file still ingests


def test_symbol_filter(db_session: Session, tmp_path: Path) -> None:
    _seed(db_session, "NABIL", "ADBL")
    _write(
        tmp_path,
        "sharesansar",
        "2026-06-16",
        ["2026-06-16,NABIL,500,510,495,505,1000", "2026-06-16,ADBL,300,310,295,305,800"],
    )

    result = _svc(db_session, tmp_path).run(symbol="NABIL")

    assert result["inserted"] == 1
    stock = db_session.scalar(sa.select(Stock).join(Price).where(Price.id > 0))
    assert stock is not None
    assert stock.symbol == "NABIL"


def test_unmapped_symbol_skipped(db_session: Session, tmp_path: Path) -> None:
    # No Stock seeded -> symbol can't resolve.
    _write(tmp_path, "sharesansar", "2026-06-16", ["2026-06-16,GHOST,500,510,495,505,1000"])

    result = _svc(db_session, tmp_path).run()

    assert result["inserted"] == 0
    assert result["unmapped_symbols"] == ["GHOST"]


def test_missing_data_dir_raises(db_session: Session, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        _svc(db_session, tmp_path / "nonexistent").run()


def test_dry_run_writes_nothing(db_session: Session, tmp_path: Path) -> None:
    _seed(db_session, "NABIL")
    _write(tmp_path, "sharesansar", "2026-06-16", ["2026-06-16,NABIL,500,510,495,505,1000"])

    result = _svc(db_session, tmp_path).run(dry_run=True)

    assert result["inserted"] == 0
    assert db_session.scalar(sa.select(sa.func.count()).select_from(Price)) == 0
