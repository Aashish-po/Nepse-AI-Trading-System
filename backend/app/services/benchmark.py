"""Benchmark service for NEPSE index, sector indices, and buy-and-hold strategies."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

import numpy as np
import sqlalchemy as sa
from sqlalchemy.orm import Session

from backend.app.db.session import SessionLocal
from backend.app.models.benchmark import NEPSEIndex, SectorIndex
from backend.app.models.price import Price
from backend.app.models.stock import Stock

logger = logging.getLogger(__name__)


class BenchmarkService:
    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    def _get_session(self) -> Session:
        if self._session is not None:
            return self._session
        return SessionLocal()

    def run_buy_and_hold(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        initial_capital: Decimal = Decimal("1000000.00"),
    ) -> dict[str, Any]:
        session = self._get_session()
        owns_session = self._session is None
        try:
            stock = session.scalar(sa.select(Stock).where(Stock.symbol == symbol.upper()))
            if stock is None:
                raise ValueError(f"Symbol {symbol} not found")

            prices = session.scalars(
                sa.select(Price)
                .where(
                    Price.stock_id == stock.id,
                    Price.date >= start_date,
                    Price.date <= end_date,
                )
                .order_by(Price.date)
            ).all()

            if not prices:
                raise ValueError(f"No price data for {symbol}")

            first_close = Decimal(str(prices[0].close)) if prices[0].close else Decimal("0")

            if first_close == 0:
                raise ValueError(f"Invalid price data for {symbol}")

            equity_curve = []
            shares = float(initial_capital / first_close)

            for price in prices:
                if price.close:
                    equity = Decimal(str(shares)) * Decimal(str(price.close))
                    equity_curve.append(
                        {
                            "date": price.date.isoformat(),
                            "equity": equity,
                            "cash": Decimal("0"),
                            "positions_value": equity,
                        }
                    )

            return self._calculate_benchmark_metrics(equity_curve)
        finally:
            if owns_session:
                session.close()

    def run_nepse_index(
        self,
        start_date: str,
        end_date: str,
        initial_capital: Decimal = Decimal("1000000.00"),
    ) -> dict[str, Any]:
        session = self._get_session()
        owns_session = self._session is None
        try:
            indices = session.scalars(
                sa.select(NEPSEIndex)
                .where(
                    NEPSEIndex.date >= start_date,
                    NEPSEIndex.date <= end_date,
                )
                .order_by(NEPSEIndex.date)
            ).all()

            if not indices:
                raise ValueError("No NEPSE index data available")

            first_close = Decimal(str(indices[0].close)) if indices[0].close else Decimal("1")
            shares = float(initial_capital / first_close)

            equity_curve = []
            for idx in indices:
                equity = Decimal(str(shares)) * Decimal(str(idx.close))
                equity_curve.append(
                    {
                        "date": idx.date.isoformat(),
                        "equity": equity,
                        "cash": Decimal("0"),
                        "positions_value": equity,
                    }
                )

            return self._calculate_benchmark_metrics(equity_curve)
        finally:
            if owns_session:
                session.close()

    def run_sector_index(
        self,
        sector: str,
        start_date: str,
        end_date: str,
        initial_capital: Decimal = Decimal("1000000.00"),
    ) -> dict[str, Any]:
        session = self._get_session()
        owns_session = self._session is None
        try:
            indices = session.scalars(
                sa.select(SectorIndex)
                .where(
                    SectorIndex.sector == sector,
                    SectorIndex.date >= start_date,
                    SectorIndex.date <= end_date,
                )
                .order_by(SectorIndex.date)
            ).all()

            if not indices:
                raise ValueError(f"No sector index data for {sector}")

            first_close = Decimal(str(indices[0].close)) if indices[0].close else Decimal("1")
            shares = float(initial_capital / first_close)

            equity_curve = []
            for idx in indices:
                equity = Decimal(str(shares)) * Decimal(str(idx.close))
                equity_curve.append(
                    {
                        "date": idx.date.isoformat(),
                        "equity": equity,
                        "cash": Decimal("0"),
                        "positions_value": equity,
                    }
                )

            return self._calculate_benchmark_metrics(equity_curve)
        finally:
            if owns_session:
                session.close()

    def _calculate_benchmark_metrics(self, equity_curve: list[dict[str, Any]]) -> dict[str, Any]:
        if not equity_curve:
            return {"period_return": 0, "annualized_return": 0, "max_drawdown": 0}

        initial_equity = equity_curve[0]["equity"]
        final_equity = equity_curve[-1]["equity"]
        period_return = (
            float((final_equity - initial_equity) / initial_equity) if initial_equity > 0 else 0
        )

        returns = []
        for i in range(1, len(equity_curve)):
            prev = equity_curve[i - 1]["equity"]
            curr = equity_curve[i]["equity"]
            if prev > 0:
                returns.append(float((curr - prev) / prev))

        max_drawdown = self._calculate_max_drawdown(equity_curve)
        sharpe = self._calculate_sharpe(returns) if returns else None

        return {
            "period_return": round(period_return, 6),
            "annualized_return": round(period_return * 252 / len(equity_curve), 6)
            if equity_curve
            else 0,
            "max_drawdown": round(max_drawdown, 6),
            "sharpe_ratio": round(sharpe, 4) if sharpe is not None else None,
            "equity_curve": equity_curve,
        }

    def _calculate_max_drawdown(self, equity_curve: list[dict[str, Any]]) -> float:
        if not equity_curve:
            return 0.0
        peak = float(equity_curve[0]["equity"])
        max_dd = 0.0
        for point in equity_curve:
            equity = float(point["equity"])
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
        return max_dd

    def _calculate_sharpe(self, returns: list[float]) -> float:
        if not returns:
            return 0.0
        arr = np.array(returns)
        mean_ret = float(np.mean(arr))
        std_ret = float(np.std(arr))
        if std_ret == 0:
            return 0.0
        return mean_ret / std_ret * (252**0.5)

    def compare_strategies(
        self,
        backtest_result: dict[str, Any],
        symbol: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        equity_curve = backtest_result.get("metrics", {}).get("equity_curve", [])

        strategy_return = 0.0
        if equity_curve:
            initial = float(equity_curve[0]["equity"])
            final = float(equity_curve[-1]["equity"])
            strategy_return = (final - initial) / initial if initial > 0 else 0

        benchmarks = {}

        if symbol and start_date and end_date:
            benchmarks["buy_and_hold"] = self.run_buy_and_hold(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
            )

        if start_date and end_date:
            benchmarks["nepse_index"] = self.run_nepse_index(
                start_date=start_date,
                end_date=end_date,
            )

        return {
            "strategy_return": strategy_return,
            "benchmark_comparison": benchmarks,
        }
