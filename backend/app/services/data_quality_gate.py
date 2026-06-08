from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.services.data_quality import DataQualityService


class DataQualityStatus(str, Enum):
    excellent = "excellent"
    warning = "warning"
    unsafe = "unsafe"


class SystemMode(str, Enum):
    normal = "NORMAL"
    degraded = "DEGRADED"
    safe_mode = "SAFE_MODE"


@dataclass(frozen=True)
class QualityGateResult:
    symbol: str
    date_str: str
    trust_score: float
    status: DataQualityStatus
    safe: bool
    details: dict[str, Any]
    components: dict[str, float]


@dataclass(frozen=True)
class SystemModeResult:
    mode: SystemMode
    total_symbols: int
    unsafe_count: int
    unsafe_ratio: float


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
        mode = self.get_system_mode()
        if mode.mode == SystemMode.safe_mode:
            raise DataQualityGateError(
                f"Feature generation suspended: system in SAFE_MODE (unsafe_ratio={mode.unsafe_ratio:.2%})"
            )
        result = self.check(symbol, date_str)
        if result.status == DataQualityStatus.unsafe:
            raise DataQualityGateError(
                f"Feature generation blocked for {symbol} on {date_str}: "
                f"trust_score={result.trust_score:.2f}, status={result.status.value}"
            )

    def assert_safe_for_backtest(self, symbol: str, date_str: str) -> None:
        mode = self.get_system_mode()
        if mode.mode == SystemMode.safe_mode:
            raise DataQualityGateError(
                f"Backtest suspended: system in SAFE_MODE (unsafe_ratio={mode.unsafe_ratio:.2%})"
            )
        result = self.check(symbol, date_str)
        if result.status == DataQualityStatus.unsafe:
            raise DataQualityGateError(
                f"Backtest excluded {symbol} on {date_str}: "
                f"trust_score={result.trust_score:.2f}, status={result.status.value}"
            )

    def get_feature_weight(self, symbol: str, date_str: str, base_weight: float = 1.0) -> float:
        mode = self.get_system_mode()
        if mode.mode == SystemMode.safe_mode:
            return 0.0
        if mode.mode == SystemMode.degraded:
            base_weight *= 0.7

        result = self.check(symbol, date_str)
        if result.status == DataQualityStatus.warning:
            return base_weight * 0.5
        if result.status == DataQualityStatus.unsafe:
            return 0.0
        return base_weight

    def get_signal_generation_allowed(self) -> bool:
        mode = self.get_system_mode()
        return mode.mode != SystemMode.safe_mode

    def get_system_mode(self) -> SystemModeResult:
        raw = self._dq.get_system_mode()
        return SystemModeResult(
            mode=SystemMode(raw["mode"]),
            total_symbols=raw.get("total_symbols", 0),
            unsafe_count=raw.get("unsafe_count", 0),
            unsafe_ratio=raw.get("unsafe_ratio", 0.0),
        )


class DataQualityGateError(Exception):
    pass
