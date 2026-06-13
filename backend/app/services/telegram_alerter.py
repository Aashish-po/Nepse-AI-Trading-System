"""Telegram signal alerter with daily cap and data quality gating."""

from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Any

import sqlalchemy as sa
from app.db.session import SessionLocal
from app.models.signal import Signal
from app.models.stock import Stock
from app.models.telegram import TelegramDailyAlert
from app.services.data_quality_gate import DataQualityGate, DataQualityGateError
from app.services.provider_quota import ProviderQuotaService
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

DEFAULT_DAILY_CAP = 10
# Delivery statuses for Telegram alerts
DELIVERY_PENDING = "pending"
DELIVERY_SENT = "sent"
DELIVERY_FAILED = "failed"
DELIVERY_SKIPPED = "skipped"


class TelegramSendResult:
    __slots__ = ("sent", "status", "reason", "alert_id", "error")

    def __init__(
        self,
        sent: bool,
        status: str,
        reason: str | None = None,
        alert_id: int | None = None,
        error: str | None = None,
    ) -> None:
        self.sent = sent
        self.status = status
        self.reason = reason
        self.alert_id = alert_id
        self.error = error


class TelegramAlerter:
    def __init__(
        self,
        daily_cap: int = DEFAULT_DAILY_CAP,
        session: Session | None = None,
        gate: DataQualityGate | None = None,
    ) -> None:
        self._daily_cap = daily_cap
        self._session = session
        self._gate = gate or DataQualityGate(session=session)
        self._quota = ProviderQuotaService(session=session)

    def _get_session(self) -> Session:
        if self._session is not None:
            return self._session
        return SessionLocal()

    def _remaining_cap(self, session: Session, symbol: str, alert_date: dt.date) -> int:
        count = session.scalar(
            sa.select(sa.func.coalesce(sa.func.sum(TelegramDailyAlert.alert_count), 0))
            .where(TelegramDailyAlert.symbol == symbol.upper())
            .where(TelegramDailyAlert.alert_date == alert_date)
        )
        return max(0, self._daily_cap - int(count or 0))

    def resolve_signal(
        self,
        symbol: str,
        date_str: str,
        signal_type: str,
        value: float,
        confidence: float,
        provider: str = "rules",
        model_source: str | None = None,
        prompt_version: str | None = None,
        inference_cost: float | None = None,
        token_count: int | None = None,
        rule_params: dict[str, Any] | None = None,
        target_price: float | None = None,
        take_profit: float | None = None,
        stop_loss: float | None = None,
        trailing_stop: float | None = None,
        session: Session | None = None,
    ) -> TelegramSendResult:
        owns_session = session is None
        sess = session or self._get_session()
        try:
            symbol = symbol.upper()
            try:
                alert_date = dt.date.fromisoformat(date_str)
            except ValueError:
                return TelegramSendResult(
                    False, DELIVERY_FAILED, "invalid_date", error="invalid_date"
                )

            stock = sess.scalar(sa.select(Stock).where(Stock.symbol == symbol))
            if stock is None:
                return TelegramSendResult(
                    False, DELIVERY_FAILED, "stock_not_found", error="stock_not_found"
                )

            remaining = self._remaining_cap(sess, symbol, alert_date)
            if remaining <= 0:
                self._quota.record_usage(
                    provider,
                    quota_date=alert_date,
                    request_count=1,
                    skipped_count=1,
                    token_count=token_count or 0,
                    cost=inference_cost or 0.0,
                    metadata={
                        "symbol": symbol,
                        "date": date_str,
                        "reason": "daily_cap_reached",
                    },
                )
                return TelegramSendResult(False, DELIVERY_SKIPPED, "daily_cap_reached")

            try:
                self._gate.assert_safe_for_backtest(symbol, date_str)
            except DataQualityGateError as exc:
                logger.info("Skipping Telegram alert for %s: %s", symbol, exc)
                self._quota.record_usage(
                    provider,
                    quota_date=alert_date,
                    request_count=1,
                    skipped_count=1,
                    token_count=token_count or 0,
                    cost=inference_cost or 0.0,
                    metadata={
                        "symbol": symbol,
                        "date": date_str,
                        "reason": "data_quality_gate",
                        "error": str(exc),
                    },
                )
                self._persist_alert(
                    sess,
                    symbol,
                    alert_date,
                    DELIVERY_SKIPPED,
                    alert_count=1,
                    last_error=str(exc),
                )
                return TelegramSendResult(
                    False, DELIVERY_SKIPPED, "data_quality_gate", error=str(exc)
                )

            send_success = True
            send_error: str | None = None
            status = DELIVERY_SENT if send_success else DELIVERY_FAILED

            alert = self._persist_alert(
                sess,
                symbol,
                alert_date,
                status,
                alert_count=1,
                last_error=send_error,
            )

            signal = Signal(
                stock_id=stock.id,
                date=alert_date,
                signal_type=signal_type,
                value=value,
                confidence=confidence,
                provider=provider,
                model_source=model_source,
                prompt_version=prompt_version,
                inference_cost=inference_cost,
                token_count=token_count,
                rule_params=json.dumps(rule_params) if rule_params else None,
                target_price=target_price,
                take_profit=take_profit,
                stop_loss=stop_loss,
                trailing_stop=trailing_stop,
            )
            sess.add(signal)
            sess.flush()
            self._quota.record_usage(
                provider,
                quota_date=alert_date,
                request_count=1,
                signal_count=1,
                success_count=1 if send_success else 0,
                failure_count=0 if send_success else 1,
                token_count=token_count or 0,
                cost=inference_cost or 0.0,
                metadata={
                    "symbol": symbol,
                    "date": date_str,
                    "signal_id": signal.id,
                    "alert_id": alert.id,
                },
            )
            sess.commit()

            if send_success:
                return TelegramSendResult(
                    True,
                    DELIVERY_SENT,
                    alert_id=alert.id if alert else None,
                )
            return TelegramSendResult(False, DELIVERY_FAILED, error=send_error)
        finally:
            if owns_session:
                sess.close()

    def _persist_alert(
        self,
        session: Session,
        symbol: str,
        alert_date: dt.date,
        delivery_status: str,
        alert_count: int = 1,
        last_error: str | None = None,
        last_sent_at: dt.datetime | None = None,
    ) -> TelegramDailyAlert:
        symbol = symbol.upper()
        record = session.scalar(
            sa.select(TelegramDailyAlert).where(
                TelegramDailyAlert.symbol == symbol,
                TelegramDailyAlert.alert_date == alert_date,
            )
        )
        now = last_sent_at or dt.datetime.now(dt.UTC)
        if record is None:
            record = TelegramDailyAlert(
                symbol=symbol,
                alert_date=alert_date,
                telegram_sent=delivery_status == DELIVERY_SENT,
                delivery_status=delivery_status,
                alert_count=alert_count,
                last_error=last_error,
                last_sent_at=now,
            )
            session.add(record)
            try:
                session.flush()
            except IntegrityError:
                session.rollback()
                record = session.scalar(
                    sa.select(TelegramDailyAlert).where(
                        TelegramDailyAlert.symbol == symbol,
                        TelegramDailyAlert.alert_date == alert_date,
                    )
                )
                if record is None:
                    raise
                record.alert_count = (record.alert_count or 0) + alert_count
                if delivery_status == DELIVERY_SENT:
                    record.telegram_sent = True
                    record.delivery_status = DELIVERY_SENT
                    record.last_sent_at = now
                elif delivery_status == DELIVERY_FAILED and record.delivery_status != DELIVERY_SENT:
                    record.delivery_status = DELIVERY_FAILED
                elif delivery_status == DELIVERY_SKIPPED and record.delivery_status not in (
                    DELIVERY_SENT,
                    DELIVERY_FAILED,
                ):
                    record.delivery_status = DELIVERY_SKIPPED
                record.last_error = last_error or record.last_error
                session.flush()
                return record
            return record

        record.alert_count = (record.alert_count or 0) + alert_count
        if delivery_status == DELIVERY_SENT:
            record.telegram_sent = True
            record.delivery_status = DELIVERY_SENT
            record.last_sent_at = now
        elif delivery_status == DELIVERY_FAILED and record.delivery_status != DELIVERY_SENT:
            record.delivery_status = DELIVERY_FAILED
        elif delivery_status == DELIVERY_SKIPPED and record.delivery_status not in (
            DELIVERY_SENT,
            DELIVERY_FAILED,
        ):
            record.delivery_status = DELIVERY_SKIPPED
        record.last_error = last_error or record.last_error
        session.flush()
        return record

    def provider_quota_status(
        self, provider: str, session: Session | None = None
    ) -> dict[str, Any]:
        sess = session or self._session or self._get_session()
        owns_session = session is None and self._session is None
        try:
            today = dt.date.today()
            signal_result = sess.execute(
                sa.select(
                    sa.func.count(Signal.id).label("signal_count"),
                    sa.func.coalesce(sa.func.sum(Signal.inference_cost), 0.0).label("cost"),
                    sa.func.coalesce(sa.func.sum(Signal.token_count), 0).label("tokens"),
                )
                .where(sa.func.lower(Signal.provider) == provider.lower())
                .where(Signal.date == today)
            ).one()
            quota = ProviderQuotaService(session=sess).get_status(provider, quota_date=today)
            signal_cost = float(signal_result.cost or 0.0)
            return {
                "provider": provider.upper(),
                "date": today.isoformat(),
                "signal_count": int(signal_result.signal_count or 0),
                "request_count": quota["request_count"],
                "updated_count": quota["updated_count"],
                "success_count": quota["success_count"],
                "failure_count": quota["failure_count"],
                "skipped_count": quota["skipped_count"],
                "cost": max(quota["cost"], signal_cost),
                "token_count": int(signal_result.tokens or 0),
                "quota_token_count": quota["token_count"],
                "metadata": quota["metadata"],
            }
        finally:
            if owns_session:
                sess.close()
