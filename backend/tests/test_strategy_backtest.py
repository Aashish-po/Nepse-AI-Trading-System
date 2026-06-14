"""Tests for Phase 5: Strategy and Backtesting MVP."""

from datetime import date, timedelta
from decimal import Decimal

from app.models.benchmark import NEPSEIndex, SectorIndex
from app.models.price import Price
from app.models.stock import Stock
from app.models.strategy import Strategy
from app.models.trade import Trade
from app.services.backtest import BacktestEngine
from app.services.benchmark import BenchmarkService
from app.services.strategy import StrategyService
from sqlalchemy import select
from sqlalchemy.orm import Session


def _seed_strategy(
    db: Session,
    name: str = "test_strategy",
    version: str = "v1.0.0",
    config: dict | None = None,
) -> Strategy:
    if config is None:
        config = {
            "symbols": ["TEST"],
            "entry_rules": [{"rule": "rsi_oversold", "params": {"threshold": 30}}],
            "exit_rules": [{"rule": "rsi_exit_long", "params": {"threshold": 70}}],
            "risk_rules": [{"rule": "max_position_size", "params": {"max_pct": 0.1}}],
        }
    strategy = Strategy(name=name, version=version, config=config)
    db.add(strategy)
    db.flush()
    db.refresh(strategy)
    return strategy


def _seed_price_data(
    db: Session,
    symbol: str,
    start_date: str,
    count: int = 60,
    base_price: float = 100.0,
) -> int:
    stock = db.scalar(select(Stock).where(Stock.symbol == symbol.upper()))
    if stock is None:
        stock = Stock(symbol=symbol.upper(), is_active=True)
        db.add(stock)
        db.flush()

    start = date.fromisoformat(start_date)
    for i in range(count):
        price_date = start + timedelta(days=i)
        close = base_price + (i - count / 2) * 0.5
        high = close + 2.0
        low = close - 2.0
        db.add(
            Price(
                stock_id=stock.id,
                date=price_date,
                open=Decimal(str(close * 0.99)),
                high=Decimal(str(high)),
                low=Decimal(str(low)),
                close=Decimal(str(close)),
                volume=1000 + i * 10,
            )
        )
    db.flush()
    return stock.id


class TestStrategyService:
    def test_create_strategy(self, db_session: Session) -> None:
        service = StrategyService(session=db_session)
        strategy = service.create_strategy(
            name="momentum",
            version="v1.0.0",
            config={"symbols": ["NEPSE"]},
        )

        assert strategy.id is not None
        assert strategy.name == "momentum"
        assert strategy.version == "v1.0.0"

    def test_get_strategy(self, db_session: Session) -> None:
        strategy = _seed_strategy(db_session)

        service = StrategyService(session=db_session)
        retrieved = service.get_strategy(strategy.id)

        assert retrieved is not None
        assert retrieved.id == strategy.id

    def test_list_strategies(self, db_session: Session) -> None:
        _seed_strategy(db_session, "strat1")
        _seed_strategy(db_session, "strat2")

        service = StrategyService(session=db_session)
        strategies = service.list_strategies(limit=10)

        assert len(strategies) >= 2

    def test_evaluate_entry_signal_rsi_oversold(self) -> None:
        service = StrategyService()
        features = {"rsi_14": 25.0, "close": 100.0}
        entry_rules = [{"rule": "rsi_oversold", "params": {"threshold": 30}}]

        result = service.evaluate_entry_signal("TEST", "2024-01-01", features, entry_rules)
        assert result is True

    def test_evaluate_entry_signal_rsi_not_oversold(self) -> None:
        service = StrategyService()
        features = {"rsi_14": 50.0, "close": 100.0}
        entry_rules = [{"rule": "rsi_oversold", "params": {"threshold": 30}}]

        result = service.evaluate_entry_signal("TEST", "2024-01-01", features, entry_rules)
        assert result is False

    def test_evaluate_exit_signal(self) -> None:
        service = StrategyService()
        features = {"rsi_14": 75.0, "close": 110.0}
        exit_rules = [{"rule": "rsi_exit_long", "params": {"threshold": 70}}]

        class MockPosition:
            quantity = 100

        result = service.evaluate_exit_signal(
            "TEST", "2024-01-01", features, exit_rules, MockPosition()
        )
        assert result is True

    def test_check_risk_rules(self) -> None:
        service = StrategyService()
        portfolio = {"cash": 1000000, "price": 100.0}
        risk_rules = [{"rule": "max_position_size", "params": {"max_pct": 0.1}}]

        result = service.check_risk_rules(portfolio, risk_rules, "TEST")
        assert "max_quantity" in result
        assert result["max_quantity"] > 0


class TestBacktestEngine:
    def test_apply_slippage_buy(self) -> None:
        engine = BacktestEngine(slippage_bps=Decimal("5.0"))
        price = Decimal("100.0")

        result = engine._apply_slippage(price, "buy")
        assert result > price
        assert result == Decimal("100.05")

    def test_apply_slippage_sell(self) -> None:
        engine = BacktestEngine(slippage_bps=Decimal("5.0"))
        price = Decimal("100.0")

        result = engine._apply_slippage(price, "sell")
        assert result < price
        assert result == Decimal("99.95")

    def test_calculate_fill_rate_high_volume(self) -> None:
        engine = BacktestEngine(partial_fill_threshold=Decimal("0.3"))
        result = engine._calculate_fill_rate(10000, 100)
        assert result == Decimal("1.0")

    def test_calculate_fill_rate_low_volume(self) -> None:
        engine = BacktestEngine(partial_fill_threshold=Decimal("0.3"))
        result = engine._calculate_fill_rate(100, 500)
        assert result < Decimal("1.0")

    def test_calculate_max_drawdown(self) -> None:
        engine = BacktestEngine()
        equity_curve = [
            {"equity": 100000, "cash": 0, "positions_value": 100000},
            {"equity": 90000, "cash": 0, "positions_value": 90000},
            {"equity": 110000, "cash": 0, "positions_value": 110000},
        ]

        result = engine._calculate_max_drawdown(equity_curve)
        assert result == 0.1

    def test_calculate_sharpe(self) -> None:
        engine = BacktestEngine()
        returns = [0.01, 0.02, -0.005, 0.015, 0.008]

        result = engine._calculate_sharpe(returns)
        assert result is not None
        assert abs(result) > 0


class TestBenchmarkService:
    def test_get_trading_dates(self) -> None:
        from app.services.backtest import BacktestEngine

        engine = BacktestEngine()
        dates = engine._get_trading_dates("2024-01-01", "2024-01-05", ["TEST"])
        assert len(dates) == 5

    def test_calculate_benchmark_metrics(self) -> None:
        service = BenchmarkService()
        equity_curve = [
            {"equity": 100000, "cash": 0, "positions_value": 100000},
            {"equity": 105000, "cash": 0, "positions_value": 105000},
            {"equity": 110000, "cash": 0, "positions_value": 110000},
        ]

        result = service._calculate_benchmark_metrics(equity_curve)
        assert result["period_return"] == 0.1
        assert "annualized_return" in result

    def test_calculate_profit_factor(self) -> None:
        engine = BacktestEngine()
        trades = [
            {"action": "BUY", "symbol": "A", "quantity": 100, "price": 100.0},
            {"action": "SELL", "symbol": "A", "quantity": 100, "price": 120.0},
            {"action": "BUY", "symbol": "B", "quantity": 100, "price": 100.0},
            {"action": "SELL", "symbol": "B", "quantity": 100, "price": 80.0},
        ]
        result = engine._calculate_profit_factor(trades)
        assert result == 1.0

    def test_calculate_expectancy(self) -> None:
        engine = BacktestEngine()
        trades = [
            {"action": "BUY", "symbol": "A", "quantity": 100, "price": 100.0},
            {"action": "SELL", "symbol": "A", "quantity": 100, "price": 105.0},
        ]
        result = engine._calculate_expectancy(trades)
        assert result == 500.0


class TestModelsIntegration:
    def test_trade_model_has_transaction_fields(self) -> None:
        trade = Trade()
        assert hasattr(trade, "transaction_cost")
        assert hasattr(trade, "fill_rate")

    def test_benchmark_models_exist(self) -> None:
        assert NEPSEIndex is not None
        assert SectorIndex is not None
        assert hasattr(NEPSEIndex, "close")
        assert hasattr(SectorIndex, "sector")
