"""Realistic backtest service with fees, slippage, liquidity, and transaction tracking."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import numpy as np
import sqlalchemy as sa
from app.db.session import SessionLocal
from app.models.backtest import Backtest
from app.models.data_quality import HolidayCalendar
from app.models.portfolio_snapshot import PortfolioSnapshot
from app.models.price import Price
from app.models.stock import Stock
from app.models.strategy import Strategy
from app.models.trade import Trade
from app.services.data_quality_gate import DataQualityGate
from app.services.feature import FeatureService
from app.services.mlflow_tracking import mlflow_tracker
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class PendingSignal:
    symbol: str
    bar_index: int
    signal_type: str


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
        start_date = start_date or "2020-01-01"
        end_date = end_date or "2024-12-31"
        positions: dict[str, Position] = {}
        cash = self.initial_capital
        equity_curve: list[dict[str, Any]] = []
        trades: list[dict[str, Any]] = []
        pending_signals: list[PendingSignal] = []

        # Deterministic backtest ID: stable hash of the inputs so repeated runs
        # with the same config produce the same ID (required for determinism tests).
        identity = hashlib.sha256(
            (
                ",".join(sorted(symbols))
                + "|"
                + start_date
                + "|"
                + end_date
                + "|"
                + strategy.name
                + "|"
                + strategy.version
            ).encode()
        ).hexdigest()[:36]

        dates = self._get_trading_dates(start_date, end_date, symbols)

        for bar_index, dt in enumerate(dates):
            date_str = dt.isoformat()

            available_prices: dict[str, dict[str, Any]] = {}
            for symbol in symbols:
                try:
                    self.gate.assert_safe_for_backtest(symbol, date_str)
                except Exception:
                    continue

                price_row = self._get_price(symbol, date_str)
                if price_row is not None:
                    available_prices[symbol] = price_row

            for signal in pending_signals[:]:
                if bar_index >= signal.bar_index + self.execution_delay_bars:
                    if signal.symbol in positions:
                        pending_signals.remove(signal)
                        continue
                    if signal.symbol not in available_prices:
                        pending_signals.remove(signal)
                        continue

                    price_row = available_prices[signal.symbol]
                    next_open = price_row.get("open") or price_row.get("close")
                    if not next_open:
                        pending_signals.remove(signal)
                        continue

                    actual_price = self._apply_slippage(Decimal(str(next_open)), "buy")
                    volume = price_row.get("volume", 0)
                    risk_rules = strategy.config.get("risk_rules", [])
                    portfolio = {
                        "cash": float(cash),
                        "price": float(next_open),
                        "initial_capital": float(self.initial_capital),
                        "positions": {s: p for s, p in positions.items()},
                    }
                    risk_result = self._check_risk(portfolio, risk_rules, signal.symbol)
                    max_qty = risk_result["max_quantity"]
                    if volume >= self.min_volume_threshold:
                        qty = min(max_qty, volume // 10)
                        fill_rate = self._calculate_fill_rate(volume, qty)
                        actual_qty = int(qty * fill_rate)

                        cost = Decimal(str(actual_qty)) * actual_price
                        cost_with_commission = cost * (1 + self.commission_rate)
                        if cash >= cost_with_commission:
                            cash -= cost_with_commission
                            positions[signal.symbol] = Position(
                                symbol=signal.symbol,
                                quantity=actual_qty,
                                entry_price=actual_price,
                                entry_date=date_str,
                                trailing_high=float(next_open),
                            )
                            trades.append(
                                {
                                    "symbol": signal.symbol,
                                    "action": "BUY",
                                    "quantity": float(actual_qty),
                                    "price": float(actual_price),
                                    "timestamp": f"{date_str}T09:00:00",
                                    "transaction_cost": float(cost * self.commission_rate),
                                    "fill_rate": float(fill_rate),
                                }
                            )
                    pending_signals.remove(signal)

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

            for symbol, price_row in available_prices.items():
                features = self._get_features(symbol, date_str)
                if features is None:
                    continue

                volume = price_row.get("volume", 0)

                if symbol in positions:
                    exit_rules = strategy.config.get("exit_rules", [])
                    pos = positions[symbol]

                    if self._should_exit(symbol, date_str, features, exit_rules, pos, price_row):
                        current_price = Decimal(str(price_row.get("close", 0)))
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

                    if self._should_enter(symbol, date_str, features, entry_rules):
                        has_pending = any(s.symbol == symbol for s in pending_signals)
                        if not has_pending:
                            pending_signals.append(
                                PendingSignal(
                                    symbol=symbol,
                                    bar_index=bar_index,
                                    signal_type="ENTRY",
                                )
                            )

        # Sort for determinism
        equity_curve = sorted(equity_curve, key=lambda x: x["date"])
        trades = sorted(trades, key=lambda x: x["timestamp"])

        metrics = self._calculate_metrics(equity_curve, trades)

        return {
            "backtest_id": identity,
            "equity_curve": self._json_safe(equity_curve),
            "trades": self._json_safe(trades),
            **metrics,
        }

    def _get_trading_dates(
        self,
        start_date: str,
        end_date: str,
        symbols: list[str],
    ) -> list[date]:
        session = SessionLocal()
        try:
            dates = []
            start = date.fromisoformat(start_date)
            end = date.fromisoformat(end_date)
            current = start
            while current <= end:
                holiday = session.scalar(
                    sa.select(HolidayCalendar).where(HolidayCalendar.date == current)
                )
                if holiday is None or holiday.is_trading_day:
                    dates.append(current)
                current += timedelta(days=1)
            return dates
        finally:
            session.close()

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
        price_row: dict[str, Any] | None = None,
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
                if position.quantity > 0 and price_row:
                    current_price = Decimal(str(price_row.get("close", 0)))
                    return_pct = (current_price - position.entry_price) / position.entry_price
                    if return_pct >= target:
                        return True
            elif rule_type == "stop_loss":
                stop = params.get("stop", 0.05)
                if position.quantity > 0 and price_row:
                    current_price = Decimal(str(price_row.get("close", 0)))
                    return_pct = (current_price - position.entry_price) / position.entry_price
                    if return_pct <= -stop:
                        return True
            elif rule_type == "trailing_stop":
                trail_pct = params.get("trail_pct", 0.10)
                if position.quantity > 0 and price_row:
                    high = price_row.get("high")
                    close = price_row.get("close")
                    if high and float(high) > position.trailing_high:
                        position.trailing_high = float(high)
                    if close:
                        close_val = float(close)
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
            "profit_factor": self._calculate_profit_factor(trades),
            "expectancy": self._calculate_expectancy(trades),
            "equity_curve": equity_curve,
            "trades": trades,
        }

    def _json_safe(self, value: Any) -> Any:
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, Mapping):
            return {key: self._json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._json_safe(item) for item in value]
        return value

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

    def _calculate_profit_factor(self, trades: list[dict[str, Any]]) -> float:
        buys = [t for t in trades if t["action"] == "BUY"]
        sells = [t for t in trades if t["action"] == "SELL"]
        if not buys or not sells:
            return 0.0

        gross_profit = Decimal("0")
        gross_loss = Decimal("0")

        for sell in sells:
            matching_buys = [b for b in buys if b["symbol"] == sell["symbol"]]
            for buy in matching_buys:
                pnl = Decimal(str(sell["price"])) * Decimal(str(sell["quantity"])) - Decimal(
                    str(buy["price"])
                ) * Decimal(str(buy["quantity"]))
                if pnl > 0:
                    gross_profit += pnl
                else:
                    gross_loss += abs(pnl)

        if gross_loss == 0:
            return float(gross_profit) if gross_profit > 0 else 0.0
        return round(float(gross_profit / gross_loss), 4)

    def _calculate_expectancy(self, trades: list[dict[str, Any]]) -> float:
        buys = [t for t in trades if t["action"] == "BUY"]
        sells = [t for t in trades if t["action"] == "SELL"]
        if not buys or not sells:
            return 0.0

        total_pnl = Decimal("0")
        trade_count = 0

        for sell in sells:
            matching_buys = [b for b in buys if b["symbol"] == sell["symbol"]]
            for buy in matching_buys:
                pnl = Decimal(str(sell["price"])) * Decimal(str(sell["quantity"])) - Decimal(
                    str(buy["price"])
                ) * Decimal(str(buy["quantity"]))
                total_pnl += pnl
                trade_count += 1

        if trade_count == 0:
            return 0.0
        return round(float(total_pnl / trade_count), 4)


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
            result = self._json_safe_metrics(result)

            backtest.metrics = result
            session.commit()

            self._persist_trades_and_snapshots(
                session, backtest.id, result["equity_curve"], result["trades"]
            )

            try:
                mlflow_tracker.log_backtest(
                    backtest_id=backtest.id,
                    strategy_id=strategy_id,
                    strategy_name=strategy.name,
                    strategy_version=strategy.version,
                    config=config,
                    metrics=result,
                    strategy_config=strategy.config,
                    symbol_count=len(symbols),
                )
            except Exception as exc:
                logger.warning("MLflow backtest logging failed: %s", exc)

            return {
                "backtest_id": backtest.id,
                "strategy_id": strategy_id,
                "metrics": result,
            }
        finally:
            if owns_session:
                session.close()

    def _json_safe_metrics(self, value: Any) -> Any:
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, Mapping):
            return {key: self._json_safe_metrics(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._json_safe_metrics(item) for item in value]
        return value

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
