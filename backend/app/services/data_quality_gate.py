from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from backend.app.services.data_quality import DataQualityService


class DataQualityStatus(str, Enum):
    excellent = "excellent"
    warning = "warning"
    unsafe = "unsafe"


@dataclass(frozen=True)
class QualityGateResult:
    symbol: str
    date_str: str
    trust_score: float
    status: DataQualityStatus
    safe: bool
    details: dict[str, Any]
    components: dict[str, float]


class DataQualityGate:
    def __init__(self, session: Any | None = None) -> None:
        self._dq = DataQualityService(session=session)

    def check(self, symbol: str, date_str: str) -> QualityGateResult:
        raw = self._dq.evaluate_symbol_date(symbol, date_str)
        return QualityGateResult(
            symbol=symbol.upper(),
            date_str=date_str,
            trust_score=raw.get("trust_score", 0.0),
            status=DataQualityStatus(raw.get("status", "unsafe")),
            safe=raw.get("safe", False),
            details=raw.get("details", {}),
            components=raw.get("components", {}),
        )

    def assert_safe_for_features(self, symbol: str, date_str: str) -> None:
        result = self.check(symbol, date_str)
        if result.status == DataQualityStatus.unsafe:
            raise DataQualityGateError(
                f"Feature generation blocked for {symbol} on {date_str}: "
                f"trust_score={result.trust_score:.2f}, status={result.status.value}"
            )

    def assert_safe_for_backtest(self, symbol: str, date_str: str) -> None:
        result = self.check(symbol, date_str)
        if result.status == DataQualityStatus.unsafe:
            raise DataQualityGateError(
                f"Backtest excluded {symbol} on {date_str}: "
                f"trust_score={result.trust_score:.2f}, status={result.status.value}"
            )

    def get_feature_weight(self, symbol: str, date_str: str, base_weight: float = 1.0) -> float:
        result = self.check(symbol, date_str)
        if result.status == DataQualityStatus.warning:
            return base_weight * 0.5
        if result.status == DataQualityStatus.unsafe:
            return 0.0
        return base_weight


class DataQualityGateError(Exception):
    pass
