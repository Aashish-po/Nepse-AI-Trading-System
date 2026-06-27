"""Position sizing with volatility and confidence adjustments."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

logger = logging.getLogger(__name__)


class SizingMethod(StrEnum):
    fixed = "fixed"
    volatility = "volatility"
    confidence = "confidence"
    hybrid = "hybrid"


@dataclass
class PositionSize:
    quantity: int
    target_value: float
    adjusted_value: float
    sizing_method: str


class PositionSizer:
    """Calculate position sizes with multiple sizing methods."""

    def __init__(
        self,
        capital: float = 100000.0,
        max_position_pct: float = 0.1,
        method: SizingMethod = SizingMethod.hybrid,
    ) -> None:
        self._capital = capital
        self._max_position_pct = max_position_pct
        self._method = method

    def calculate(
        self,
        price: float,
        confidence: float,
        volatility: float | None = None,
    ) -> PositionSize:
        method = self._method.value

        target_value = self._capital * self._max_position_pct

        match method:
            case "fixed":
                adjusted = target_value
            case "confidence":
                adjusted = target_value * max(0.0, min(1.0, confidence))
            case "volatility":
                if volatility is not None and volatility > 0:
                    vol_factor = 1.0 / max(volatility, 0.001)
                    adjusted = target_value / (1.0 + vol_factor)
                else:
                    adjusted = target_value
            case "hybrid":
                conf_factor = max(0.0, min(1.0, confidence))
                vol_factor = 1.0 / max(volatility or 0.01, 0.001)
                adjusted = target_value * conf_factor * (1.0 / (1.0 + vol_factor))
            case _:
                adjusted = target_value

        quantity = int(adjusted / price) if price > 0 else 0
        return PositionSize(
            quantity=quantity,
            target_value=target_value,
            adjusted_value=adjusted,
            sizing_method=method,
        )
