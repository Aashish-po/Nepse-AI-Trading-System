"""Dashboard analytics service (Phase 13).

Aggregations powering the dashboard: market overview, signal explorer, and
portfolio analytics. All read-only and advisory.
"""

from __future__ import annotations

import logging
from typing import Any

import sqlalchemy as sa
from app.models.price import Price
from app.models.signal import Signal
from app.models.stock import Stock
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Compute dashboard-facing aggregations over market and signal data."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ----------------------------------------------------------- market overview
    def market_overview(self, top_n: int = 5) -> dict[str, Any]:
        """Summarize the market: counts plus top gainers/losers by latest return."""
        total_stocks = self._session.scalar(sa.select(sa.func.count(Stock.id))) or 0
        active_stocks = (
            self._session.scalar(
                sa.select(sa.func.count(Stock.id)).where(Stock.is_active.is_(True))
            )
            or 0
        )
        latest_date = self._session.scalar(sa.select(sa.func.max(Price.date)))

        movers = self._compute_movers(top_n=top_n)
        return {
            "total_stocks": int(total_stocks),
            "active_stocks": int(active_stocks),
            "latest_date": latest_date.isoformat() if latest_date else None,
            "top_gainers": movers["gainers"],
            "top_losers": movers["losers"],
        }

    def _compute_movers(self, top_n: int) -> dict[str, list[dict[str, Any]]]:
        """Compute the latest close-over-previous-close return per stock."""
        rows = self._session.execute(
            sa.select(Price.stock_id, Price.date, Price.close, Stock.symbol)
            .join(Stock, Price.stock_id == Stock.id)
            .where(Price.close.is_not(None))
            .order_by(Price.stock_id, Price.date.desc())
        ).all()

        # Collect the two most recent closes per stock.
        by_stock: dict[int, list[Any]] = {}
        symbols: dict[int, str] = {}
        for stock_id, _date, close, symbol in rows:
            symbols[stock_id] = symbol
            bucket = by_stock.setdefault(stock_id, [])
            if len(bucket) < 2:
                bucket.append(close)

        changes: list[dict[str, Any]] = []
        for stock_id, closes in by_stock.items():
            if len(closes) < 2 or closes[1] in (None, 0):
                continue
            latest, prev = float(closes[0]), float(closes[1])
            if prev == 0:
                continue
            pct = (latest - prev) / prev * 100.0
            changes.append(
                {"symbol": symbols[stock_id], "close": latest, "change_pct": round(pct, 4)}
            )

        changes.sort(key=lambda c: c["change_pct"], reverse=True)
        gainers = [c for c in changes if c["change_pct"] > 0][:top_n]
        losers = [c for c in changes if c["change_pct"] < 0]
        losers = sorted(losers, key=lambda c: c["change_pct"])[:top_n]
        return {"gainers": gainers, "losers": losers}

    # ------------------------------------------------------------ signal explorer
    def explore_signals(
        self,
        symbol: str | None = None,
        signal_type: str | None = None,
        provider: str | None = None,
        min_confidence: float | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """List signals with optional filters plus summary statistics."""
        query = (
            sa.select(Signal, Stock.symbol)
            .join(Stock, Signal.stock_id == Stock.id)
            .order_by(Signal.date.desc())
        )
        if symbol:
            query = query.where(Stock.symbol == symbol.upper())
        if signal_type:
            query = query.where(Signal.signal_type == signal_type)
        if provider:
            query = query.where(sa.func.lower(Signal.provider) == provider.lower())
        if min_confidence is not None:
            query = query.where(Signal.confidence >= min_confidence)

        rows = self._session.execute(query.limit(limit)).all()
        signals = [
            {
                "id": sig.id,
                "symbol": sym,
                "date": sig.date.isoformat(),
                "signal_type": sig.signal_type,
                "value": float(sig.value) if sig.value is not None else None,
                "confidence": float(sig.confidence) if sig.confidence is not None else None,
                "provider": sig.provider,
            }
            for sig, sym in rows
        ]

        confidences = [s["confidence"] for s in signals if s["confidence"] is not None]
        summary = {
            "count": len(signals),
            "avg_confidence": round(sum(confidences) / len(confidences), 4)
            if confidences
            else None,
            "by_type": self._count_by(signals, "signal_type"),
            "by_provider": self._count_by(signals, "provider"),
        }
        return {"signals": signals, "summary": summary}

    @staticmethod
    def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in items:
            value = item.get(key) or "unknown"
            counts[value] = counts.get(value, 0) + 1
        return counts

    # --------------------------------------------------------- portfolio analytics
    def portfolio_analytics(self, equity_curve: list[float]) -> dict[str, Any]:
        """Compute risk/return analytics from an equity curve.

        Returns total return, annualized volatility, Sharpe, and max drawdown.
        """
        if not equity_curve or len(equity_curve) < 2:
            return {
                "total_return": 0.0,
                "volatility": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
                "n_periods": len(equity_curve),
            }

        import numpy as np

        equity = np.asarray(equity_curve, dtype=np.float64)
        returns = np.diff(equity) / np.where(equity[:-1] == 0, np.nan, equity[:-1])
        returns = returns[~np.isnan(returns)]

        total_return = float((equity[-1] - equity[0]) / equity[0]) if equity[0] else 0.0
        vol = float(np.std(returns) * np.sqrt(252)) if returns.size else 0.0
        mean = float(np.mean(returns)) if returns.size else 0.0
        std = float(np.std(returns)) if returns.size else 0.0
        sharpe = (mean / std * np.sqrt(252)) if std > 0 else 0.0

        peak = np.maximum.accumulate(equity)
        drawdown = (peak - equity) / np.where(peak == 0, 1.0, peak)
        max_dd = float(np.max(drawdown))

        return {
            "total_return": round(total_return, 6),
            "volatility": round(vol, 6),
            "sharpe_ratio": round(float(sharpe), 6),
            "max_drawdown": round(max_dd, 6),
            "n_periods": len(equity_curve),
        }
