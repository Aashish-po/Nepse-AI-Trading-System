"""Idempotent rule-based signal backfill over Price history."""

from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Any

import sqlalchemy as sa
from app.db.session import SessionLocal
from app.models.price import Price
from app.models.signal import Signal
from app.models.stock import Stock
from app.services.data_quality_gate import DataQualityGate, DataQualityGateError
from app.services.feature import FeatureService
from app.services.provider_quota import ProviderQuotaService
from app.services.strategy import StrategyService
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

DEFAULT_ENTRY_RULES: list[dict[str, Any]] = [
    {"rule": "rsi_oversold", "params": {"threshold": 30}},
    {"rule": "sma_cross_up"},
]
DEFAULT_EXIT_RULES: list[dict[str, Any]] = [
    {"rule": "rsi_exit_long", "params": {"threshold": 70}},
    {"rule": "sma_cross_down"},
]


class SignalBackfillService:
    def __init__(
        self,
        session: Session | None = None,
        gate: DataQualityGate | None = None,
        feature_service: FeatureService | None = None,
        strategy_service: StrategyService | None = None,
    ) -> None:
        self._session = session
        self._gate = gate or DataQualityGate(session=session)
        self._features = feature_service or FeatureService(gate=self._gate, session=session)
        self._strategy = strategy_service or StrategyService(session=session)

    def _quota_service(self, session: Session) -> ProviderQuotaService:
        return ProviderQuotaService(session=session)

    def backfill_all(
        self,
        start_date: str,
        end_date: str | None = None,
        symbols: list[str] | None = None,
        entry_rules: list[dict[str, Any]] | None = None,
        exit_rules: list[dict[str, Any]] | None = None,
        risk_rules: list[dict[str, Any]] | None = None,
        upsert: bool = True,
    ) -> dict[str, Any]:
        session = self._session or SessionLocal()
        owns_session = self._session is None
        requested_symbols = [symbol.upper() for symbol in symbols or []]
        try:
            query = sa.select(Stock)
            if requested_symbols:
                query = query.where(Stock.symbol.in_(requested_symbols))
            else:
                query = query.where(Stock.is_active.is_(True))
            query = query.order_by(Stock.symbol)
            stocks = list(session.scalars(query).all())

            results: dict[str, dict[str, int]] = {}
            errors: list[dict[str, str]] = []
            for stock in stocks:
                try:
                    results[stock.symbol] = self.backfill_symbol(
                        stock.symbol,
                        start_date=start_date,
                        end_date=end_date,
                        entry_rules=entry_rules,
                        exit_rules=exit_rules,
                        risk_rules=risk_rules,
                        upsert=upsert,
                    )
                except Exception as exc:  # noqa: BLE001
                    errors.append({"symbol": stock.symbol, "error": str(exc)})
                    logger.warning("Backfill failed for %s: %s", stock.symbol, exc)

            return {
                "symbols_requested": len(requested_symbols) if requested_symbols else len(stocks),
                "symbols_succeeded": len(results),
                "symbols_failed": len(errors),
                "results": results,
                "errors": errors,
            }
        finally:
            if owns_session:
                session.close()

    def backfill_symbol(
        self,
        symbol: str,
        start_date: str,
        end_date: str | None = None,
        entry_rules: list[dict[str, Any]] | None = None,
        exit_rules: list[dict[str, Any]] | None = None,
        risk_rules: list[dict[str, Any]] | None = None,
        upsert: bool = True,
    ) -> dict[str, int]:
        session = self._session or SessionLocal()
        owns_session = self._session is None
        try:
            active_entry_rules = entry_rules if entry_rules is not None else DEFAULT_ENTRY_RULES
            active_exit_rules = exit_rules if exit_rules is not None else DEFAULT_EXIT_RULES
            stock = session.scalar(sa.select(Stock).where(Stock.symbol == symbol.upper()))
            if stock is None:
                raise ValueError(f"Stock {symbol} not found")

            end = dt.date.fromisoformat(end_date) if end_date else dt.date.today()
            start = dt.date.fromisoformat(start_date)
            dates = [
                dt.date.fromisoformat(row[0]) if isinstance(row[0], str) else row[0]
                for row in session.execute(
                    sa.select(Price.date)
                    .where(Price.stock_id == stock.id)
                    .where(Price.date >= start)
                    .where(Price.date <= end)
                    .order_by(Price.date)
                ).all()
            ]

            created = 0
            updated = 0
            skipped = 0
            for date_obj in dates:
                date_str = date_obj.isoformat()
                try:
                    if not self._gate.get_signal_generation_allowed():
                        skipped += 1
                        continue
                    features = self._features.compute_features(symbol, date_str).get("features", {})
                    close = features.get("close")
                    if self._strategy.evaluate_entry_signal(
                        symbol, date_str, features, active_entry_rules
                    ):
                        signal_type = "entry"
                        confidence = float(features.get("confidence") or 0.0)
                    elif self._strategy.evaluate_exit_signal(
                        symbol, date_str, features, active_exit_rules, position=None
                    ):
                        signal_type = "exit"
                        confidence = float(features.get("confidence") or 0.0)
                    else:
                        skipped += 1
                        continue

                    signal_payload = {
                        "signal_type": signal_type,
                        "confidence": confidence,
                        "provider": "rules",
                        "rule_params": json.dumps(
                            {"entry_rules": active_entry_rules, "exit_rules": active_exit_rules}
                        ),
                        "value": close if close is not None else 0.0,
                    }

                    existing = session.scalar(
                        sa.select(Signal)
                        .where(Signal.stock_id == stock.id)
                        .where(Signal.date == date_obj)
                        .where(Signal.signal_type == signal_type)
                        .limit(1)
                    )
                    if existing is None:
                        session.add(
                            Signal(
                                stock_id=stock.id,
                                date=date_obj,
                                **signal_payload,
                            )
                        )
                        created += 1
                        self._quota_service(session).record_usage(
                            "rules",
                            quota_date=date_obj,
                            request_count=0,
                            signal_count=1,
                            metadata={
                                "symbol": symbol.upper(),
                                "date": date_str,
                                "signal_type": signal_type,
                                "operation": "created",
                            },
                        )
                    elif upsert:
                        for key, value in signal_payload.items():
                            if key == "rule_params":
                                setattr(existing, key, value)
                            else:
                                setattr(existing, key, value)
                        existing.confidence = confidence
                        updated += 1
                        self._quota_service(session).record_usage(
                            "rules",
                            quota_date=date_obj,
                            request_count=0,
                            updated_count=1,
                            metadata={
                                "symbol": symbol.upper(),
                                "date": date_str,
                                "signal_type": signal_type,
                                "operation": "updated",
                            },
                        )
                    else:
                        skipped += 1
                except DataQualityGateError:
                    skipped += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Backfill failed for %s on %s: %s", symbol, date_str, exc)
                    skipped += 1
            session.commit()
            return {"created": created, "updated": updated, "skipped": skipped}
        finally:
            if owns_session:
                session.close()
