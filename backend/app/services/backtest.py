"""Backtest execution service with data quality enforcement."""

from __future__ import annotations

from typing import Any

from backend.app.services.data_quality_gate import DataQualityGate, DataQualityGateError


class BacktestService:
    def __init__(self, gate: DataQualityGate | None = None) -> None:
        self._gate = gate or DataQualityGate()

    def run_backtest(self, symbol: str, start_date: str, end_date: str) -> dict[str, Any]:
        excluded: list[str] = []
        included: list[str] = []
        for day in self._date_range(start_date, end_date):
            try:
                self._gate.assert_safe_for_backtest(symbol, day)
                included.append(day)
            except DataQualityGateError:
                excluded.append(day)

        return {
            "symbol": symbol.upper(),
            "start_date": start_date,
            "end_date": end_date,
            "included_days": len(included),
            "excluded_days": len(excluded),
            "excluded_dates": excluded[:10],
        }

    def _date_range(self, start_date: str, end_date: str) -> list[str]:
        from datetime import date, timedelta

        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        dates = []
        current = start
        while current <= end:
            dates.append(current.isoformat())
            current += timedelta(days=1)
        return dates
