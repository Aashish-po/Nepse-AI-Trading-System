"""Risk management layer for trading strategies."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RiskState:
    equity: float
    peak_equity: float
    drawdown: float
    max_drawdown: float
    positions_exposure: dict[str, float]
    total_exposure: float


@dataclass
class RiskDecision:
    allow_trade: bool
    reason: str | None = None


class RiskManager:
    """Manages portfolio-level risk constraints."""

    def __init__(
        self,
        max_drawdown: float = 0.2,
        max_exposure_per_asset: float = 0.15,
        stop_loss_pct: float = 0.05,
        take_profit_pct: float = 0.10,
    ) -> None:
        self._max_drawdown = max_drawdown
        self._max_exposure_per_asset = max_exposure_per_asset
        self._stop_loss_pct = stop_loss_pct
        self._take_profit_pct = take_profit_pct
        self._peak_equity: float = 0.0
        self._max_drawdown_seen: float = 0.0

    @property
    def max_drawdown(self) -> float:
        """Return the configured maximum drawdown threshold."""
        return self._max_drawdown

    def evaluate(self, symbol: str, equity: float, positions: dict[str, float]) -> RiskState:
        if equity > self._peak_equity:
            self._peak_equity = equity

        drawdown = (
            (equity - self._peak_equity) / self._peak_equity if self._peak_equity > 0 else 0.0
        )
        if drawdown < -self._max_drawdown_seen:
            self._max_drawdown_seen = drawdown
        total_exposure = sum(positions.values())

        return RiskState(
            equity=equity,
            peak_equity=self._peak_equity,
            drawdown=drawdown,
            max_drawdown=self._max_drawdown_seen,
            positions_exposure={s: v for s, v in positions.items()},
            total_exposure=total_exposure,
        )

    def check_trade(
        self, symbol: str, value: float, equity: float, positions: dict[str, Any]
    ) -> RiskDecision:
        state = self.evaluate(symbol, equity, positions)

        if state.drawdown <= -self._max_drawdown:
            return RiskDecision(allow_trade=False, reason="max_drawdown_exceeded")

        if symbol in positions:
            exposure = positions[symbol] / equity if equity > 0 else 0
            if exposure + (value / equity if equity > 0 else 0) > self._max_exposure_per_asset:
                return RiskDecision(allow_trade=False, reason="exposure_limit")

        return RiskDecision(allow_trade=True)


class StopLossManager:
    """Track stop-loss and take-profit levels per position."""

    def __init__(self) -> None:
        self._entry_prices: dict[str, float] = {}
        self._stop_losses: dict[str, float] = {}
        self._take_profits: dict[str, float] = {}

    def set_entry(self, symbol: str, entry_price: float) -> None:
        self._entry_prices[symbol] = entry_price
        self._stop_losses[symbol] = entry_price * (1 - 0.05)
        self._take_profits[symbol] = entry_price * (1 + 0.10)

    def check_exit(self, symbol: str, current_price: float) -> str | None:
        if symbol not in self._entry_prices:
            return None

        if current_price <= self._stop_losses.get(symbol, 0):
            return "stop_loss"
        if current_price >= self._take_profits.get(symbol, float("inf")):
            return "take_profit"
        return None

    def remove(self, symbol: str) -> None:
        self._entry_prices.pop(symbol, None)
        self._stop_losses.pop(symbol, None)
        self._take_profits.pop(symbol, None)
