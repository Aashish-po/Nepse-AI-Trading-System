"""Realistic backtest service with fees, slippage, liquidity, and transaction tracking."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import numpy as np
import sqlalchemy as sa
from sqlalchemy.orm import Session

from backend.app.db.session import SessionLocal
from backend.app.models.backtest import Backtest
from backend.app.models.portfolio_snapshot import PortfolioSnapshot
from backend.app.models.price import Price
from backend.app.models.stock import Stock
from backend.app.models.strategy import Strategy
from backend.app.models.trade import Trade
from backend.app.services.data_quality_gate import DataQualityGate
from backend.app.services.feature import FeatureService

logger = logging.getLogger(__name__)


@dataclass
class Position:
    symbol: str
    quantity: int
    entry_price: Decimal
    entry_date: str
    trailing_high: float = 0.0

    @property
    def market_value(self) -> Decimal:
        return Decimal(str(self.quantity)) * Decimal(str(self.entry_price))


@dataclass
class Transaction:
    symbol: str
    action: str
    quantity: int
    price: Decimal
    timestamp: datetime
    transaction_cost: Decimal
    fill_rate: Decimal


class BacktestEngine:
    def __init__(
        self,
        initial_capital: Decimal = Decimal("1000000.00"),
        commission_rate: Decimal = Decimal("0.005"),
        slippage_bps: Decimal = Decimal("5.0"),
        min_volume_threshold: int = 100,
        partial_fill_threshold: Decimal = Decimal("0.3"),
        execution_delay_bars: int = 1,
        data_quality_gate: DataQualityGate | None = None,
    ) -> None:
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage_rate = partial_fill_threshold
        self.slippage_bps = slippage_bps
        self.min_volume_threshold = min_volume_threshold
        self.partial_fill_threshold = partial_fill_threshold
        self.execution_delay_bars = execution_delay_bars
        self.gate = data_quality_gate or DataQualityGate()
        self.feature_service = FeatureService()

    def run(
        self,
        strategy: Strategy,
        symbols: list[str],
        start_date: str | None,
        end_date: str | None,
    ) -> dict[str, Any]:
        # Normalize date params with defaults
        start_date = start_date or "2020-01-01"
        end_date = end_date or "2024-12-31"
        positions: dict[str, Position] = {}
        cash = self.initial_capital
        equity_curve: list[dict[str, Any]] = []
        trades: list[dict[str, Any]] = []
        date_prices: dict[str, dict[str, Decimal]] = {}

        dates = self._get_trading_dates(start_date, end_date, symbols)

        for dt in dates:
            date_str = dt.isoformat()
            positions_value = sum(p.market_value for p in positions.values())
            equity = Decimal(str(cash)) + positions_value
            equity_curve.append(
                {
                    "date": date_str,
                    "equity": equity,
                    "cash": Decimal(str(cash)),
                    "positions_value": positions_value,
                }
            )

            for symbol in symbols:
                try:
                    self.gate.assert_safe_for_backtest(symbol, date_str)
                except Exception:
                    continue

                price_row = self._get_price(symbol, date_str)
                if price_row is None:
                    continue
                date_prices[symbol] = price_row

                features = self._get_features(symbol, date_str)
                if features is None:
                    continue

                current_price = Decimal(str(price_row.get("close", 0)))
                volume = price_row.get("volume", 0)

                if symbol in positions:
                    exit_rules = strategy.config.get("exit_rules", [])
                    pos = positions[symbol]

                    if self._should_exit(symbol, date_str, features, exit_rules, pos):
                        exit_price = self._apply_slippage(current_price, "sell")
                        fill_rate = self._calculate_fill_rate(volume, pos.quantity)
                        actual_qty = int(pos.quantity * fill_rate)
                        actual_price = exit_price

                        proceeds = Decimal(str(actual_qty)) * actual_price
                        cost = proceeds * self.commission_rate
                        cash += proceeds - cost

                        trades.append(
                            {
                                "symbol": symbol,
                                "action": "SELL",
                                "quantity": float(actual_qty),
                                "price": float(actual_price),
                                "timestamp": f"{date_str}T15:00:00",
                                "transaction_cost": float(cost),
                                "fill_rate": float(fill_rate),
                            }
                        )
                        del positions[symbol]
                else:
                    entry_rules = strategy.config.get("entry_rules", [])
                    risk_rules = strategy.config.get("risk_rules", [])

                    if self._should_enter(symbol, date_str, features, entry_rules):
                        portfolio = {
                            "cash": float(cash),
                            "price": float(current_price),
                            "initial_capital": float(self.initial_capital),
                            "positions": {s: p for s, p in positions.items()},
                        }
                        risk_result = self._check_risk(portfolio, risk_rules, symbol)
                        if risk_result["max_quantity"] > 0 and volume >= self.min_volume_threshold:
                            qty = min(risk_result["max_quantity"], volume // 10)
                            buy_price = self._apply_slippage(current_price, "buy")
                            fill_rate = self._calculate_fill_rate(volume, qty)
                            actual_qty = int(qty * fill_rate)
                            actual_price = buy_price

                            cost = Decimal(str(actual_qty)) * actual_price
                            cost_with_commission = cost * (1 + self.commission_rate)
                            if cash >= cost_with_commission:
                                cash -= cost_with_commission
                                positions[symbol] = Position(
                                    symbol=symbol,
                                    quantity=actual_qty,
                                    entry_price=actual_price,
                                    entry_date=date_str,
                                    trailing_high=float(actual_price),
                                )
                                trades.append(
                                    {
                                        "symbol": symbol,
                                        "action": "BUY",
                                        "quantity": float(actual_qty),
                                        "price": float(actual_price),
                                        "timestamp": f"{date_str}T09:00:00",
                                        "transaction_cost": float(cost * self.commission_rate),
                                        "fill_rate": float(fill_rate),
                                    }
                                )

        return self._calculate_metrics(equity_curve, trades)

    def _get_trading_dates(self, start_date: str, end_date: str, symbols: list[str]) -> list[date]:
        dates = []
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        current = start
        while current <= end:
            dates.append(current)
            current += timedelta(days=1)
        return dates

    def _get_price(self, symbol: str, date_str: str) -> dict[str, Any] | None:
        session = SessionLocal()
        try:
            stock = session.scalar(sa.select(Stock).where(Stock.symbol == symbol.upper()))
            if stock is None:
                return None
            price = session.scalar(
                sa.select(Price).where(
                    Price.stock_id == stock.id,
                    Price.date == date.fromisoformat(date_str),
                )
            )
            if price is None:
                return None
            return {
                "open": float(price.open) if price.open else None,
                "high": float(price.high) if price.high else None,
                "low": float(price.low) if price.low else None,
                "close": float(price.close) if price.close else None,
                "volume": price.volume,
            }
        finally:
            session.close()

    def _get_features(self, symbol: str, date_str: str) -> dict[str, float | None] | None:
        try:
            features = self.feature_service.get_features(symbol, date_str)
            if features is None:
                return None
            return features.get("features", {})
        except Exception:
            return None

    def _should_enter(
        self,
        symbol: str,
        date_str: str,
        features: Mapping[str, float | None],
        entry_rules: list[dict],
    ) -> bool:
        for rule in entry_rules:
            rule_type = rule.get("rule")
            params = rule.get("params", {})

            if rule_type == "rsi_oversold":
                rsi = features.get("rsi_14")
                if rsi is not None and rsi < params.get("threshold", 30):
                    return True
            elif rule_type == "rsi_overbought":
                rsi = features.get("rsi_14")
                if rsi is not None and rsi > params.get("threshold", 70):
                    return True
            elif rule_type == "sma_cross_up":
                sma_20 = features.get("sma_20")
                sma_50 = features.get("sma_50")
                if sma_20 is not None and sma_50 is not None and sma_20 > sma_50:
                    return True
            elif rule_type == "macd_cross_up":
                macd = features.get("macd")
                signal = features.get("macd_signal")
                if macd is not None and signal is not None and macd > signal:
                    return True
            elif rule_type == "breakout_high":
                close = features.get("close")
                if close is not None and close > params.get("threshold", 105.0):
                    return True
        return False

    def _should_exit(
        self,
        symbol: str,
        date_str: str,
        features: Mapping[str, float | None],
        exit_rules: list[dict],
        position: Position,
    ) -> bool:
        for rule in exit_rules:
            rule_type = rule.get("rule")
            params = rule.get("params", {})

            if rule_type == "rsi_exit_long":
                rsi = features.get("rsi_14")
                if rsi is not None and rsi > params.get("threshold", 70):
                    return True
            elif rule_type == "take_profit":
                target = params.get("target", 0.1)
                if position.quantity > 0:
                    current_price = Decimal(str(features.get("close", 0)))
                    return_pct = (current_price - position.entry_price) / position.entry_price
                    if return_pct >= target:
                        return True
            elif rule_type == "stop_loss":
                stop = params.get("stop", 0.05)
                if position.quantity > 0:
                    current_price = Decimal(str(features.get("close", 0)))
                    return_pct = (current_price - position.entry_price) / position.entry_price
                    if return_pct <= -stop:
                        return True
            elif rule_type == "trailing_stop":
                trail_pct = params.get("trail_pct", 0.10)
                if position.quantity > 0:
                    close = features.get("close")
                    if close:
                        close_val = float(close)
                        if close_val > position.trailing_high:
                            position.trailing_high = close_val
                        trail_level = position.trailing_high * (1 - trail_pct)
                        if close_val < trail_level:
                            return True

        return False

    def _check_risk(
        self,
        portfolio: dict[str, Any],
        risk_rules: list[dict],
        symbol: str,
    ) -> dict[str, Any]:
        cash = portfolio.get("cash", 0)
        initial_capital = portfolio.get("initial_capital", cash)
        price = portfolio.get("price", 1)
        positions = portfolio.get("positions", {})

        max_qty = int(cash / price) if price > 0 else 0

        for rule in risk_rules:
            rule_type = rule.get("rule")
            params = rule.get("params", {})

            if rule_type == "max_position_size":
                max_pct = params.get("max_pct", 0.1)
                max_qty = int(min(max_qty, cash * max_pct / price))
            elif rule_type == "single_stock_exposure":
                max_pct = params.get("max_pct", 0.2)
                max_shares = int(portfolio.get("cash", 0) * max_pct / price)
                max_qty = min(max_qty, max_shares)
            elif rule_type == "max_open_positions":
                max_pos = params.get("max_count", 5)
                if len(positions) >= max_pos:
                    return {"max_quantity": 0}
            elif rule_type == "cash_reserve":
                reserve_pct = params.get("reserve_pct", 0.1)
                reserve_amount = initial_capital * reserve_pct
                available_cash = cash - reserve_amount
                max_shares = int(available_cash / price) if price > 0 and available_cash > 0 else 0
                max_qty = min(max_qty, max_shares)

        return {"max_quantity": max(0, max_qty)}

    def _apply_slippage(self, price: Decimal, action: str) -> Decimal:
        slippage_factor = Decimal(str(self.slippage_bps)) / Decimal("10000")
        if action == "buy":
            return price * (1 + slippage_factor)
        return price * (1 - slippage_factor)

    def _calculate_fill_rate(self, volume: int, desired_qty: int) -> Decimal:
        if desired_qty <= 0:
            return Decimal("0")
        max_fill = Decimal(str(volume)) * Decimal(str(self.partial_fill_threshold))
        if desired_qty <= volume * 0.3:
            return Decimal("1.0")
        return min(Decimal("0.7"), max_fill / Decimal(str(desired_qty)))

    def _calculate_metrics(
        self, equity_curve: list[dict[str, Any]], trades: list[dict[str, Any]]
    ) -> dict[str, Any]:
        if not equity_curve:
            return {"total_trades": 0, "total_return": 0, "equity_curve": []}

        total_trades = len(trades)
        initial_equity = equity_curve[0]["equity"]
        final_equity = equity_curve[-1]["equity"]

        total_return = (
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
            "total_trades": total_trades,
            "total_return": round(total_return, 6),
            "annualized_return": round(total_return * 252 / len(equity_curve), 6)
            if equity_curve
            else 0,
            "max_drawdown": round(max_drawdown, 6),
            "sharpe_ratio": round(sharpe, 4) if sharpe is not None else None,
            "win_rate": self._calculate_win_rate(trades),
            "equity_curve": equity_curve,
            "trades": trades,
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
        mean_ret = np.mean(arr)
        std_ret = np.std(arr)
        if std_ret == 0:
            return 0.0
        return float(mean_ret / std_ret * (252**0.5))

    def _calculate_win_rate(self, trades: list[dict[str, Any]]) -> float:
        buys = [t for t in trades if t["action"] == "BUY"]
        sells = [t for t in trades if t["action"] == "SELL"]
        if not buys or not sells:
            return 0.0
        profitable = 0
        for buy in buys:
            matching_sells = [s for s in sells if s["symbol"] == buy["symbol"]]
            for sell in matching_sells:
                if sell["price"] > buy["price"]:
                    profitable += 1
                    break
        return round(profitable / len(buys), 4) if buys else 0.0


class BacktestService:
    def __init__(self, session: Session | None = None) -> None:
        self._session = session
        self._engine: BacktestEngine | None = None

    def _get_session(self) -> Session:
        if self._session is not None:
            return self._session
        return SessionLocal()

    def _get_engine(self) -> BacktestEngine:
        if self._engine is not None:
            return self._engine
        owns_session = self._session is None
        session = self._get_session()
        self._engine = BacktestEngine(data_quality_gate=DataQualityGate(session=session))
        if owns_session:
            pass
        return self._engine

    def run_backtest(
        self,
        strategy_id: int,
        config: dict,
    ) -> dict[str, Any]:
        session = self._get_session()
        owns_session = self._session is None
        try:
            strategy = session.get(Strategy, strategy_id)
            if strategy is None:
                raise ValueError(f"Strategy {strategy_id} not found")

            backtest = Backtest(
                strategy_id=strategy_id,
                config=config,
            )
            session.add(backtest)
            session.commit()
            session.refresh(backtest)

            engine = self._get_engine()
            symbols = strategy.config.get("symbols", [])
            if not symbols:
                raise ValueError("Strategy has no symbols configured")

            result = engine.run(
                strategy=strategy,
                symbols=symbols,
                start_date=config.get("start_date"),
                end_date=config.get("end_date"),
            )

            backtest.metrics = result
            session.commit()

            self._persist_trades_and_snapshots(
                session, backtest.id, result["equity_curve"], result["trades"]
            )

            return {
                "backtest_id": backtest.id,
                "strategy_id": strategy_id,
                "metrics": result,
            }
        finally:
            if owns_session:
                session.close()

    def _persist_trades_and_snapshots(
        self,
        session: Session,
        backtest_id: int,
        equity_curve: list[dict[str, Any]],
        trades: list[dict[str, Any]],
    ) -> None:
        for trade in trades:
            stock = session.scalar(sa.select(Stock).where(Stock.symbol == trade["symbol"].upper()))
            if stock is None:
                continue
            db_trade = Trade(
                backtest_id=backtest_id,
                stock_id=stock.id,
                action=trade["action"],
                quantity=int(trade["quantity"]),
                price=Decimal(str(trade["price"])),
                timestamp=datetime.fromisoformat(trade["timestamp"]),
                transaction_cost=Decimal(str(trade.get("transaction_cost", 0)))
                if trade.get("transaction_cost")
                else None,
                fill_rate=Decimal(str(trade.get("fill_rate", 1.0)))
                if trade.get("fill_rate")
                else None,
            )
            session.add(db_trade)

        for point in equity_curve:
            snapshot = PortfolioSnapshot(
                backtest_id=backtest_id,
                date=date.fromisoformat(point["date"]),
                equity=Decimal(str(point["equity"])),
                cash=Decimal(str(point["cash"])),
                positions={},
            )
            session.add(snapshot)

        session.commit()
