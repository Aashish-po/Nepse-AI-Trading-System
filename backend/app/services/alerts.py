"""Rule-based alerting engine (Phase 13).

Evaluates alert rules against recent market and signal data and produces alert
notifications. Rules are declarative dicts so the dashboard can manage them
without code changes. Delivery is delegated to the existing Telegram alerter
when requested; otherwise alerts are returned for in-dashboard display.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy as sa
from app.models.price import Price
from app.models.signal import Signal
from app.models.stock import Stock
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Supported rule kinds
RULE_PRICE_CHANGE = "price_change_pct"
RULE_SIGNAL_CONFIDENCE = "signal_confidence"
RULE_VOLUME_SPIKE = "volume_spike"

SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"


@dataclass
class Alert:
    rule_name: str
    kind: str
    symbol: str
    severity: str
    message: str
    triggered_at: str
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_name": self.rule_name,
            "kind": self.kind,
            "symbol": self.symbol,
            "severity": self.severity,
            "message": self.message,
            "triggered_at": self.triggered_at,
            "context": self.context,
        }


class AlertEngine:
    """Evaluate declarative alert rules against the database."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def evaluate_rules(self, rules: list[dict[str, Any]]) -> list[Alert]:
        alerts: list[Alert] = []
        for rule in rules:
            kind = rule.get("kind")
            try:
                if kind == RULE_PRICE_CHANGE:
                    alerts.extend(self._eval_price_change(rule))
                elif kind == RULE_SIGNAL_CONFIDENCE:
                    alerts.extend(self._eval_signal_confidence(rule))
                elif kind == RULE_VOLUME_SPIKE:
                    alerts.extend(self._eval_volume_spike(rule))
                else:
                    logger.warning("Unknown alert rule kind: %s", kind)
            except Exception:  # pragma: no cover - defensive per-rule isolation
                logger.exception("Alert rule '%s' evaluation failed", rule.get("name"))
        return alerts

    def _now(self) -> str:
        return dt.datetime.now(dt.UTC).isoformat()

    def _latest_two_closes(self, symbol: str) -> tuple[float, float] | None:
        rows = self._session.execute(
            sa.select(Price.close)
            .join(Stock, Price.stock_id == Stock.id)
            .where(Stock.symbol == symbol.upper(), Price.close.is_not(None))
            .order_by(Price.date.desc())
            .limit(2)
        ).all()
        if len(rows) < 2 or rows[1][0] in (None, 0):
            return None
        return float(rows[0][0]), float(rows[1][0])

    def _eval_price_change(self, rule: dict[str, Any]) -> list[Alert]:
        symbol = rule["symbol"].upper()
        threshold = float(rule.get("threshold_pct", 5.0))
        closes = self._latest_two_closes(symbol)
        if closes is None:
            return []
        latest, prev = closes
        pct = (latest - prev) / prev * 100.0 if prev else 0.0
        if abs(pct) < abs(threshold):
            return []
        severity = SEVERITY_CRITICAL if abs(pct) >= abs(threshold) * 2 else SEVERITY_WARNING
        direction = "up" if pct > 0 else "down"
        return [
            Alert(
                rule_name=rule.get("name", "price_change"),
                kind=RULE_PRICE_CHANGE,
                symbol=symbol,
                severity=severity,
                message=f"{symbol} moved {pct:.2f}% ({direction}), threshold {threshold}%",
                triggered_at=self._now(),
                context={"change_pct": round(pct, 4), "close": latest, "prev_close": prev},
            )
        ]

    def _eval_signal_confidence(self, rule: dict[str, Any]) -> list[Alert]:
        min_conf = float(rule.get("min_confidence", 0.8))
        signal_type = rule.get("signal_type")
        lookback_days = int(rule.get("lookback_days", 7))
        since = dt.date.today() - dt.timedelta(days=lookback_days)

        query = (
            sa.select(Signal, Stock.symbol)
            .join(Stock, Signal.stock_id == Stock.id)
            .where(Signal.confidence >= min_conf, Signal.date >= since)
            .order_by(Signal.date.desc())
        )
        if "symbol" in rule:
            query = query.where(Stock.symbol == rule["symbol"].upper())
        if signal_type:
            query = query.where(Signal.signal_type == signal_type)

        alerts: list[Alert] = []
        for sig, symbol in self._session.execute(query).all():
            alerts.append(
                Alert(
                    rule_name=rule.get("name", "high_confidence_signal"),
                    kind=RULE_SIGNAL_CONFIDENCE,
                    symbol=symbol,
                    severity=SEVERITY_INFO,
                    message=(
                        f"{symbol} {sig.signal_type} signal at "
                        f"{float(sig.confidence):.0%} confidence"
                    ),
                    triggered_at=self._now(),
                    context={
                        "signal_id": sig.id,
                        "confidence": float(sig.confidence),
                        "value": float(sig.value) if sig.value is not None else None,
                        "date": sig.date.isoformat(),
                    },
                )
            )
        return alerts

    def _eval_volume_spike(self, rule: dict[str, Any]) -> list[Alert]:
        symbol = rule["symbol"].upper()
        multiplier = float(rule.get("multiplier", 3.0))
        window = int(rule.get("window", 20))

        rows = self._session.execute(
            sa.select(Price.volume)
            .join(Stock, Price.stock_id == Stock.id)
            .where(Stock.symbol == symbol, Price.volume.is_not(None))
            .order_by(Price.date.desc())
            .limit(window + 1)
        ).all()
        volumes = [float(r[0]) for r in rows if r[0] is not None]
        if len(volumes) < 2:
            return []
        latest = volumes[0]
        history = volumes[1:]
        avg = sum(history) / len(history) if history else 0.0
        if avg <= 0 or latest < avg * multiplier:
            return []
        return [
            Alert(
                rule_name=rule.get("name", "volume_spike"),
                kind=RULE_VOLUME_SPIKE,
                symbol=symbol,
                severity=SEVERITY_WARNING,
                message=f"{symbol} volume {latest:.0f} is {latest / avg:.1f}x the {window}-day avg",
                triggered_at=self._now(),
                context={"latest_volume": latest, "avg_volume": round(avg, 2)},
            )
        ]
