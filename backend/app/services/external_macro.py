"""Macro ingestion service (FRED).

Fetches macro observations for a configured set of series, normalises them, and
upserts idempotently into ``macro_series`` / ``macro_observations``. Every run is
recorded in ``IngestionLog``. Provider/network failures are logged and surfaced
in the returned summary but never raised into feature generation or fusion.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime
from typing import Any

import sqlalchemy as sa
from app.core.config import Settings, settings as default_settings
from app.db.session import SessionLocal
from app.models.data_source import IngestionLog
from app.models.macro import MacroObservation, MacroSeries
from app.services.external.fred import PROVIDER as FRED_PROVIDER, FredClient
from app.services.external.providers import PROVIDERS_BY_KEY, ensure_data_source, is_enabled
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class MacroIngestionService:
    """Ingest FRED macro series into the database (manual / on-demand)."""

    def __init__(
        self,
        cfg: Settings | None = None,
        *,
        session: Session | None = None,
        client: FredClient | None = None,
    ) -> None:
        self._cfg = cfg or default_settings
        self._session = session
        self._client = client

    def _get_session(self) -> Session:
        return self._session if self._session is not None else SessionLocal()

    def _default_series(self) -> list[str]:
        return [s.strip() for s in self._cfg.fred_default_series.split(",") if s.strip()]

    def run(
        self, series_ids: list[str] | None = None, *, today: date | None = None
    ) -> dict[str, Any]:
        """Ingest the given (or default) FRED series.

        Returns a summary dict; never raises on provider failure.
        """
        spec = PROVIDERS_BY_KEY["fred"]
        if not is_enabled(spec, self._cfg):
            logger.info("macro ingest skipped: FRED not enabled/keyed")
            return {"status": "skipped", "reason": "provider_disabled", "series": {}}

        series_ids = series_ids or self._default_series()
        today = today or datetime.now(UTC).date()
        session = self._get_session()
        owns_session = self._session is None
        client = self._client or FredClient(self._cfg)
        owns_client = self._client is None

        start_time = datetime.now(UTC)
        log = IngestionLog(
            source=FRED_PROVIDER,
            status="failed",
            started_at=start_time,
            completed_at=start_time,
        )
        session.add(log)
        session.commit()
        log_id = log.id
        del log

        ensure_data_source(session, spec)
        session.commit()

        per_series: dict[str, Any] = {}
        total_fetched = 0
        total_inserted = 0
        try:
            for series_id in series_ids:
                result = self._ingest_one(session, client, series_id, today=today)
                per_series[series_id] = result
                total_fetched += result.get("fetched", 0)
                total_inserted += result.get("inserted", 0)

            completed_at = datetime.now(UTC)
            failed = [s for s, r in per_series.items() if r.get("status") == "failed"]
            session.query(IngestionLog).filter(IngestionLog.id == log_id).update(
                {
                    "status": "success",
                    "records_fetched": total_fetched,
                    "records_inserted": total_inserted,
                    "records_rejected": 0,
                    "duration_seconds": (completed_at - start_time).total_seconds(),
                    "errors": json.dumps({"failed_series": failed}) if failed else None,
                    "completed_at": completed_at,
                }
            )
            session.commit()
            return {
                "status": "success",
                "fetched": total_fetched,
                "inserted": total_inserted,
                "series": per_series,
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
            logger.exception("macro ingest failed")
            return {
                "status": "failed",
                "error": str(exc),
                "fetched": total_fetched,
                "inserted": total_inserted,
                "series": per_series,
            }
        finally:
            if owns_client:
                client.close()
            if owns_session:
                session.close()

    def _ingest_one(
        self,
        session: Session,
        client: FredClient,
        series_id: str,
        *,
        today: date,
    ) -> dict[str, Any]:
        try:
            meta = client.get_series_metadata(series_id)
            rows = client.get_observations(series_id, today=today)
            series = self._upsert_series(session, meta)
            inserted = self._upsert_observations(session, series.id, rows)
            session.commit()
            return {"status": "success", "fetched": len(rows), "inserted": inserted}
        except Exception as exc:  # noqa: BLE001
            logger.warning("fred series %s ingest failed: %s", series_id, exc)
            session.rollback()  # Clean up partial transaction
            return {"status": "failed", "error": str(exc), "fetched": 0, "inserted": 0}

    def _upsert_series(self, session: Session, meta: dict[str, Any]) -> MacroSeries:
        series = session.scalar(
            sa.select(MacroSeries).where(
                MacroSeries.provider == FRED_PROVIDER,
                MacroSeries.series_id == meta["series_id"],
            )
        )
        if series is None:
            series = MacroSeries(
                provider=FRED_PROVIDER,
                series_id=meta["series_id"],
                name=meta.get("name"),
                units=meta.get("units"),
                frequency=meta.get("frequency"),
                is_active=True,
            )
            session.add(series)
            session.flush()
        else:
            series.name = meta.get("name") or series.name
            series.units = meta.get("units") or series.units
            series.frequency = meta.get("frequency") or series.frequency
        return series

    def _upsert_observations(
        self,
        session: Session,
        series_pk: int,
        rows: list[dict[str, Any]],
    ) -> int:
        inserted = 0
        for row in rows:
            try:
                with session.begin_nested():
                    existing = session.scalar(
                        sa.select(MacroObservation).where(
                            MacroObservation.macro_series_id == series_pk,
                            MacroObservation.date == row["date"],
                        )
                    )
                    if existing is not None:
                        existing.value = row["value"]
                        raw_data = row.get("raw")
                        # The FRED client always includes raw data in observations
                        existing.raw_json = raw_data if raw_data is not None else {}
                        continue
                    session.add(
                        MacroObservation(
                            macro_series_id=series_pk,
                            date=row["date"],
                            value=row["value"],
                            raw_json=row.get("raw") or {},
                        )
                    )
                    inserted += 1
            except SQLAlchemyError:
                logger.warning(
                    "macro obs upsert failed for series %s date %s", series_pk, row["date"]
                )
                continue
        return inserted
