"""External market (OHLCV) ingestion service — Marketstack / Finnhub.

Fetches global/benchmark OHLCV for a set of provider symbols, validates against
OHLCV invariants, and upserts idempotently into ``external_prices`` (separate
from NEPSE ``Price`` data). Each run is logged in ``IngestionLog``. Provider and
network failures are logged and surfaced in the summary but never raised into
feature generation or fusion. A missing provider/symbol does not affect NEPSE
ingestion.

Manual / on-demand only (no scheduler).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from app.core.config import Settings, settings as default_settings
from app.db.session import SessionLocal
from app.models.data_source import IngestionLog
from app.models.external_market import ExternalPrice, ExternalSymbol
from app.services.external.base import ExternalApiClient
from app.services.external.finnhub import PROVIDER as FINNHUB, FinnhubClient
from app.services.external.marketstack import PROVIDER as MARKETSTACK, MarketstackClient
from app.services.external.providers import PROVIDERS_BY_KEY, ensure_data_source, is_enabled
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK_DAYS = 400

_CLIENTS = {MARKETSTACK: MarketstackClient, FINNHUB: FinnhubClient}


class MarketIngestionService:
    """Ingest external OHLCV for one provider (``marketstack`` or ``finnhub``)."""

    def __init__(
        self,
        provider: str,
        cfg: Settings | None = None,
        *,
        session: Session | None = None,
        client: ExternalApiClient | None = None,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    ) -> None:
        if provider not in _CLIENTS:
            raise ValueError(f"Unsupported market provider: {provider}")
        self._provider = provider
        self._cfg = cfg or default_settings
        self._session = session
        self._client = client
        self._lookback_days = lookback_days

    def _get_session(self) -> Session:
        return self._session if self._session is not None else SessionLocal()

    def run(self, symbols: list[str], *, today: date | None = None) -> dict[str, Any]:
        """Ingest OHLCV for each symbol. Returns a summary; never raises."""
        spec = PROVIDERS_BY_KEY[self._provider]
        if not is_enabled(spec, self._cfg):
            logger.info("market ingest skipped: %s not enabled/keyed", self._provider)
            return {"status": "skipped", "reason": "provider_disabled", "symbols": {}}

        today = today or datetime.now(UTC).date()
        session = self._get_session()
        owns_session = self._session is None
        client = self._client or _CLIENTS[self._provider](self._cfg)
        owns_client = self._client is None

        start_time = datetime.now(UTC)
        log = IngestionLog(
            source=self._provider, status="failed", started_at=start_time, completed_at=start_time
        )
        session.add(log)
        session.commit()
        log_id = log.id
        del log

        ensure_data_source(session, spec)
        session.commit()

        per_symbol: dict[str, Any] = {}
        total_fetched = 0
        total_inserted = 0
        try:
            for symbol in symbols:
                result = self._ingest_one(session, client, symbol.upper(), today)
                per_symbol[symbol] = result
                total_fetched += result.get("fetched", 0)
                total_inserted += result.get("inserted", 0)

            completed_at = datetime.now(UTC)
            failed = [s for s, r in per_symbol.items() if r.get("status") == "failed"]
            session.query(IngestionLog).filter(IngestionLog.id == log_id).update(
                {
                    "status": "success",
                    "records_fetched": total_fetched,
                    "records_inserted": total_inserted,
                    "records_rejected": total_fetched - total_inserted,
                    "duration_seconds": (completed_at - start_time).total_seconds(),
                    "errors": json.dumps({"failed_symbols": failed}) if failed else None,
                    "completed_at": completed_at,
                }
            )
            session.commit()
            return {
                "status": "success",
                "fetched": total_fetched,
                "inserted": total_inserted,
                "symbols": per_symbol,
            }
        except Exception as exc:  # noqa: BLE001 — provider failure must not propagate
            completed_at = datetime.now(UTC)
            session.query(IngestionLog).filter(IngestionLog.id == log_id).update(
                {
                    "status": "failed",
                    "records_fetched": total_fetched,
                    "records_inserted": total_inserted,
                    "duration_seconds": (completed_at - start_time).total_seconds(),
                    "errors": json.dumps({"exception": str(exc)}),
                    "completed_at": completed_at,
                }
            )
            session.commit()
            logger.exception("market ingest failed for %s", self._provider)
            return {
                "status": "failed",
                "error": str(exc),
                "fetched": total_fetched,
                "inserted": total_inserted,
                "symbols": per_symbol,
            }
        finally:
            if owns_client:
                client.close()
            if owns_session:
                session.close()

    def _fetch(self, client: ExternalApiClient, symbol: str, today: date) -> list[dict[str, Any]]:
        start = today - timedelta(days=self._lookback_days)
        if self._provider == MARKETSTACK:
            return client.get_eod(  # type: ignore[attr-defined]
                symbol, date_from=start.isoformat(), date_to=today.isoformat(), today=today
            )
        from_ts = int(datetime(start.year, start.month, start.day, tzinfo=UTC).timestamp())
        to_ts = int(datetime(today.year, today.month, today.day, tzinfo=UTC).timestamp())
        return client.get_candles(  # type: ignore[attr-defined]
            symbol, from_ts=from_ts, to_ts=to_ts, today=today
        )

    def _ingest_one(
        self, session: Session, client: ExternalApiClient, symbol: str, today: date
    ) -> dict[str, Any]:
        try:
            rows = self._fetch(client, symbol, today)
            self._ensure_symbol(session, symbol)
            inserted = sum(1 for row in rows if self._upsert_price(session, row))
            session.commit()
            return {"status": "success", "fetched": len(rows), "inserted": inserted}
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s ingest for %s failed: %s", self._provider, symbol, exc)
            session.rollback()
            return {"status": "failed", "error": str(exc), "fetched": 0, "inserted": 0}

    def _ensure_symbol(self, session: Session, symbol: str) -> None:
        existing = session.scalar(
            sa.select(ExternalSymbol).where(
                ExternalSymbol.provider == self._provider,
                ExternalSymbol.external_symbol == symbol,
            )
        )
        if existing is None:
            session.add(
                ExternalSymbol(provider=self._provider, external_symbol=symbol, is_active=True)
            )
            session.flush()

    def _upsert_price(self, session: Session, row: dict[str, Any]) -> bool:
        """Insert a price row if new (by provider/symbol/date). Returns True if created."""
        try:
            with session.begin_nested():
                existing = session.scalar(
                    sa.select(ExternalPrice).where(
                        ExternalPrice.provider == row["provider"],
                        ExternalPrice.external_symbol == row["external_symbol"],
                        ExternalPrice.date == row["date"],
                    )
                )
                if existing is not None:
                    return False
                session.add(
                    ExternalPrice(
                        provider=row["provider"],
                        external_symbol=row["external_symbol"],
                        date=row["date"],
                        open=row["open"],
                        high=row["high"],
                        low=row["low"],
                        close=row["close"],
                        volume=row["volume"],
                        currency=row.get("currency"),
                        raw_json=row.get("raw"),
                    )
                )
                session.flush()
        except SQLAlchemyError as exc:
            logger.warning("external price upsert failed: %s", exc)
            return False
        return True
