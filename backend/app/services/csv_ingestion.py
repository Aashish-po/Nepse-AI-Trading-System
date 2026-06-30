"""Ingest NEPSE price CSVs produced by ``nepse_data/scraper.py`` into ``Price``.

Read-only over the scraper output: the scraper runs independently (cron/manual)
and writes ``nepse_data/data/{sharesansar,merolagani}/YYYY-MM-DD.csv``; this
service parses those files, normalizes them to OHLCV, merges the two sources,
and upserts on ``(stock_id, date)``.

Both sources already carry a NEPSE ``Symbol`` column, so there is no
company-name resolution. ShareSansar is daily OHLCV; Merolagani is a tick-level
floor sheet that we aggregate per symbol.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import sqlalchemy as sa
from app.db.session import session_scope
from app.models.data_source import IngestionLog
from app.models.price import Price
from app.models.stock import Stock
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Project root: .../services -> app -> backend -> <root>; scraper writes here.
DEFAULT_CSV_DIR = Path(__file__).resolve().parents[3] / "nepse_data" / "data"
SOURCES = ("sharesansar", "merolagani")
_MISSING = {"", "-", "--", "n/a", "na", "nan", "none"}


def _num(v: Any) -> float | None:
    """Parse a scraped cell ('835,407.30', '--', '') to float or None."""
    s = str(v).strip().replace(",", "").lower()
    if s in _MISSING:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _completeness(row: dict[str, Any]) -> int:
    return sum(row[k] is not None for k in ("open", "high", "low", "close"))


def _valid_ohlcv(r: dict[str, Any]) -> bool:
    o, h, lo, c = r["open"], r["high"], r["low"], r["close"]
    if all(x is None for x in (o, h, lo, c)):
        return False
    if h is not None and lo is not None and h < lo:
        return False
    if h is not None and any(x is not None and x > h for x in (o, c)):
        return False
    if lo is not None and any(x is not None and x < lo for x in (o, c)):
        return False
    return not (r["volume"] is not None and r["volume"] < 0)


def _pick(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Merge tiebreak for the same (symbol, date): completeness, then volume,
    then prefer ShareSansar."""
    if _completeness(a) != _completeness(b):
        return a if _completeness(a) > _completeness(b) else b
    va, vb = a["volume"] or 0, b["volume"] or 0
    if va != vb:
        return a if va > vb else b
    return a if a["source"] == "sharesansar" else b


def _read_sharesansar(path: Path, file_date: date) -> list[dict[str, Any]] | None:
    df = pd.read_csv(path)
    df.columns = pd.Index([str(col).strip().lower() for col in df.columns])
    if {"symbol", "open", "high", "low", "close", "vol"} - set(df.columns):
        return None
    return [
        {
            "symbol": str(r["symbol"]).strip().upper(),
            "date": file_date,
            "open": _num(r["open"]),
            "high": _num(r["high"]),
            "low": _num(r["low"]),
            "close": _num(r["close"]),
            "volume": int(_num(r["vol"]) or 0),
            "source": "sharesansar",
        }
        for _, r in df.iterrows()
        if str(r["symbol"]).strip()
    ]


def _read_merolagani(path: Path, file_date: date) -> list[dict[str, Any]] | None:
    df = pd.read_csv(path)
    df.columns = pd.Index([str(col).strip().lower() for col in df.columns])
    if {"symbol", "rate", "quantity"} - set(df.columns):
        return None
    df["rate"] = df["rate"].map(_num)
    df["quantity"] = df["quantity"].map(lambda v: _num(v) or 0)
    # ponytail: open/close from floor-sheet '#' order (ascending = first trade).
    # Contract numbering is a proxy for time order; high/low/volume are exact.
    order = "#" if "#" in df.columns else None
    rows: list[dict[str, Any]] = []
    for sym, g in df.groupby("symbol"):
        if order:
            g = g.sort_values(order)
        rates = g["rate"].dropna()
        if rates.empty:
            continue
        rows.append(
            {
                "symbol": str(sym).strip().upper(),
                "date": file_date,
                "open": float(rates.iloc[0]),
                "high": float(rates.max()),
                "low": float(rates.min()),
                "close": float(rates.iloc[-1]),
                "volume": int(g["quantity"].sum()),
                "source": "merolagani",
            }
        )
    return rows


_READERS = {"sharesansar": _read_sharesansar, "merolagani": _read_merolagani}


class CsvIngestionService:
    def __init__(
        self,
        session: Session | None = None,
        csv_dir: Path | str | None = None,
        source: str = "csv_ingestion",
    ) -> None:
        self._session = session
        self.csv_dir = Path(csv_dir) if csv_dir else DEFAULT_CSV_DIR
        self.source = source

    def run(
        self,
        symbol: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        start = date.fromisoformat(start_date) if start_date else date.min
        end = date.fromisoformat(end_date) if end_date else date.max

        if not self.csv_dir.exists() or not any(self.csv_dir.glob("*/*.csv")):
            raise FileNotFoundError(
                f"No CSV data found in {self.csv_dir} — run python nepse_data/scraper.py first"
            )

        rows: list[dict[str, Any]] = []
        files_processed = holiday_skips = schema_errors = 0
        for src in SOURCES:
            src_dir = self.csv_dir / src
            if not src_dir.is_dir():
                continue
            for path in sorted(src_dir.glob("*.csv")):
                try:
                    file_date = date.fromisoformat(path.stem)
                except ValueError:
                    continue
                if not (start <= file_date <= end):
                    continue
                parsed = _READERS[src](path, file_date)
                if parsed is None:
                    schema_errors += 1
                    logger.warning("schema mismatch, skipping %s", path)
                    continue
                files_processed += 1
                if not parsed:
                    holiday_skips += 1
                    continue
                logger.info("processed file: %s, rows=%d, source=%s", path, len(parsed), src)
                rows.extend(parsed)

        fetched = len(rows)
        if symbol:
            rows = [r for r in rows if r["symbol"] == symbol.upper()]
        rows = [r for r in rows if _valid_ohlcv(r)]

        merged: dict[tuple[str, date], dict[str, Any]] = {}
        for r in rows:
            key = (r["symbol"], r["date"])
            merged[key] = r if key not in merged else _pick(merged[key], r)
        final = list(merged.values())

        with session_scope(self._session) as session:
            rows_result = session.execute(sa.select(Stock.symbol, Stock.id)).all()
            stock_ids: dict[str, int] = {str(r[0]): int(r[1]) for r in rows_result}
            unmapped = sorted({r["symbol"] for r in final if r["symbol"] not in stock_ids})
            for sym in unmapped:
                logger.warning("unmapped symbol skipped: %s (no Stock row)", sym)
            to_insert = [r for r in final if r["symbol"] in stock_ids]

            base = {
                "fetched": fetched,
                "files_processed": files_processed,
                "holiday_skips": holiday_skips,
                "schema_errors": schema_errors,
                "unmapped_symbols": unmapped,
            }
            if dry_run:
                return {**base, "inserted": 0, "updated": 0, "rejected": fetched}

            inserted, updated = self._upsert(session, to_insert, stock_ids)
            rejected = fetched - inserted - updated
            self._log_run(session, fetched, inserted, rejected, unmapped)
            return {**base, "inserted": inserted, "updated": updated, "rejected": rejected}

    def _upsert(
        self,
        session: Session,
        rows: list[dict[str, Any]],
        stock_ids: dict[str, int],
    ) -> tuple[int, int]:
        inserted = updated = 0
        for r in rows:
            try:
                with session.begin_nested():
                    existing = session.scalar(
                        sa.select(Price).where(
                            Price.stock_id == stock_ids[r["symbol"]],
                            Price.date == r["date"],
                        )
                    )
                    if existing is None:
                        session.add(Price(stock_id=stock_ids[r["symbol"]], **_price_fields(r)))
                        inserted += 1
                    else:
                        for k, v in _price_fields(r).items():
                            setattr(existing, k, v)
                        updated += 1
                    session.flush()
            except SQLAlchemyError:
                logger.exception("upsert failed for %s@%s", r["symbol"], r["date"])
        session.commit()
        return inserted, updated

    def _log_run(
        self,
        session: Session,
        fetched: int,
        inserted: int,
        rejected: int,
        unmapped: list[str],
    ) -> None:
        now = datetime.now(UTC)
        errors = json.dumps({"unmapped_symbols": unmapped[:20]}) if unmapped else None
        session.add(
            IngestionLog(
                source=self.source,
                status="success",
                records_fetched=fetched,
                records_inserted=inserted,
                records_rejected=rejected,
                duration_seconds=0.0,
                errors=errors,
                started_at=now,
                completed_at=now,
            )
        )
        session.commit()


def _price_fields(r: dict[str, Any]) -> dict[str, Any]:
    return {k: r[k] for k in ("date", "open", "high", "low", "close", "volume")}
