"""Feature computation service with data quality enforcement."""

from __future__ import annotations

from typing import Any

from backend.app.services.data_quality_gate import DataQualityGate


class FeatureService:
    def __init__(self, gate: DataQualityGate | None = None) -> None:
        self._gate = gate or DataQualityGate()

    def compute_features(self, symbol: str, date_str: str) -> dict[str, Any]:
        self._gate.assert_safe_for_features(symbol, date_str)
        return self._build_features(symbol, date_str)

    def _build_features(self, symbol: str, date_str: str) -> dict[str, Any]:
        return {
            "symbol": symbol.upper(),
            "date": date_str,
            "features": {
                "returns": 0.0,
                "volatility": 0.0,
                "volume_ratio": 0.0,
            },
        }
