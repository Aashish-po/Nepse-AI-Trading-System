from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.db.session import SessionLocal
from backend.app.models.data_source import IngestionLog
from backend.app.models.price import Price
from backend.app.models.stock import Stock
from backend.app.services.data_quality import DataQualityService

MAX_RETRIES = 3


class IngestionService:
    def __init__(self, source: str = "primary", session: Session | None = None) -> None:
        self.source = source
        self._session = session

    def _get_session(self) -> Session:
        if self._session is not None:
            return self._session
        return SessionLocal()

    def run(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, int]:
        session = self._get_session()
        owns_session = self._session is None
        start_time = datetime.now(UTC)
        log = IngestionLog(
            source=self.source,
            status="failed",
            started_at=start_time,
            completed_at=start_time,
        )
        session.add(log)
        session.commit()
        log_id = log.id
        del log

        raw_data: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        try:
            raw_data = self._fetch_with_retry(symbol, start_date, end_date)
            session.query(IngestionLog).filter(IngestionLog.id == log_id).update(
                {"records_fetched": len(raw_data)}
            )
            session.commit()

            valid, rejected = self._validate(raw_data)
            self._detect_missing_dates(valid, rejected)
            normalized = self._normalize(valid, symbol)
            inserted = 0
            if not dry_run:
                inserted = self._insert(session, normalized)

            completed_at = datetime.now(UTC)
            duration = (completed_at - start_time).total_seconds()
            error_payload = None
            if rejected:
                error_payload = json.dumps(
                    {
                        "exception": "validation_failed",
                        "sample_rejected": rejected[:5],
                    }
                )
            session.query(IngestionLog).filter(IngestionLog.id == log_id).update(
                {
                    "status": "success",
                    "records_inserted": inserted,
                    "records_rejected": len(rejected),
                    "duration_seconds": duration,
                    "errors": error_payload,
                    "completed_at": completed_at,
                }
            )
            session.commit()

            if inserted > 0 and not dry_run:
                try:
                    dq = DataQualityService(session=session)
                    for r in normalized:
                        dq.evaluate_symbol_date(r["symbol"], r["date"].isoformat(), session=session)
                except Exception:  # noqa: BLE001
                    pass

            return {
                "fetched": len(raw_data),
                "inserted": inserted,
                "rejected": len(rejected),
            }
        except Exception as e:  # noqa: BLE001
            completed_at = datetime.now(UTC)
            duration = (completed_at - start_time).total_seconds()
            error_payload = json.dumps(
                {
                    "exception": str(e),
                    "sample_rejected": rejected[:5],
                }
            )
            session.query(IngestionLog).filter(IngestionLog.id == log_id).update(
                {
                    "status": "failed",
                    "records_fetched": len(raw_data),
                    "records_rejected": len(rejected),
                    "duration_seconds": duration,
                    "errors": error_payload,
                    "completed_at": completed_at,
                }
            )
            session.commit()
            raise
        finally:
            if owns_session:
                session.close()

    def _fetch_with_retry(
        self,
        symbol: str,
        start_date: str | None,
        end_date: str | None,
    ) -> list[dict[str, Any]]:
        last_exception: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                return self.fetch(symbol, start_date, end_date)
            except Exception as e:  # noqa: BLE001
                last_exception = e
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2**attempt)
        raise last_exception or RuntimeError("fetch failed")

    def fetch(
        self,
        symbol: str,
        start_date: str | None,
        end_date: str | None,
    ) -> list[dict[str, Any]]:
        _start = start_date or (datetime.now(UTC).date() - timedelta(days=30)).isoformat()
        return [
            {
                "date": "2024-01-01",
                "open": 100.0,
                "high": 110.0,
                "low": 95.0,
                "close": 105.0,
                "volume": 2000,
            }
        ]

    def _validate(
        self,
        rows: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        valid: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        for row in rows:
            try:
                if not all(k in row for k in ["date", "open", "high", "low", "close", "volume"]):
                    raise ValueError("missing required fields")
                if row["open"] > row["high"]:
                    raise ValueError("open > high")
                if row["low"] > row["high"]:
                    raise ValueError("low > high")
                if row["volume"] < 0:
                    raise ValueError("negative volume")
                valid.append(row)
            except Exception as e:  # noqa: BLE001
                rejected.append({**row, "error": str(e)})
        return valid, rejected

    def _detect_missing_dates(
        self,
        valid: list[dict[str, Any]],
        rejected: list[dict[str, Any]],
    ) -> None:
        try:
            dates = sorted(
                datetime.fromisoformat(r["date"]).date() for r in valid if "date" in r
            )
            missing: list[tuple[str, str]] = []
            for i in range(1, len(dates)):
                gap = (dates[i] - dates[i - 1]).days
                if gap > 1:
                    missing.append((dates[i - 1].isoformat(), dates[i].isoformat()))
            if missing:
                rejected.append(
                    {
                        "error": f"missing dates: {missing[:3]}",
                    }
                )
        except Exception:  # noqa: BLE001
            pass

    def _normalize(
        self,
        rows: list[dict[str, Any]],
        symbol: str,
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for r in rows:
            normalized.append(
                {
                    "symbol": symbol,
                    "date": datetime.fromisoformat(r["date"]).date(),
                    "open": float(r["open"]),
                    "high": float(r["high"]),
                    "low": float(r["low"]),
                    "close": float(r["close"]),
                    "volume": int(r["volume"]),
                }
            )
        return normalized

    def _insert(self, session: Session, rows: list[dict[str, Any]]) -> int:
        inserted = 0
        for r in rows:
            try:
                with session.begin_nested():
                    stock = session.scalar(
                        sa.select(Stock).where(Stock.symbol == r["symbol"].upper())
                    )
                    if stock is None:
                        stock = Stock(symbol=r["symbol"].upper(), is_active=True)
                        session.add(stock)
                        session.flush()
                    price = Price(
                        stock_id=stock.id,
                        date=r["date"],
                        open=r["open"],
                        high=r["high"],
                        low=r["low"],
                        close=r["close"],
                        volume=r["volume"],
                    )
                    session.add(price)
                    session.flush()
                inserted += 1
            except SQLAlchemyError:
                continue
        session.commit()
        return inserted
