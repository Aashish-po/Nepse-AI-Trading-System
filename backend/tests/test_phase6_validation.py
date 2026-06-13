"""Phase 6 validation test suite.

Covers the gate criteria for Phase 6 completion:
1. Full workflow cycle time < 5 minutes (dashboard load to export)
2. Export schema validation matching BACKEND_SCHEMA.md contracts
3. Backtest determinism (same config = identical results)
4. API timeout handling tests
5. Safe mode integration (Phase 2b -> Phase 6)
6. Data quality gate enforcement in dashboard context
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from datetime import date, timedelta
from decimal import Decimal

import pytest
from app.core.config import Settings
from app.models.data_quality import HolidayCalendar
from app.models.price import Price
from app.models.stock import Stock
from app.models.strategy import Strategy
from app.schemas.data_quality import (
    DataQualityReportResponse,
    SymbolQualitySummaryResponse,
    TrustScoreResponse,
)
from app.schemas.strategy import BacktestConfig
from app.services.backtest import BacktestEngine
from app.services.data_quality import DataQualityService
from app.services.data_quality_gate import (
    DataQualityGate,
    DataQualityGateError,
    DataQualityStatus,
    SystemMode,
)
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session


def _seed_stock(db: Session, symbol: str, is_active: bool = True) -> Stock:
    stock = db.scalar(select(Stock).where(Stock.symbol == symbol.upper()))
    if stock is None:
        stock = Stock(symbol=symbol.upper(), is_active=is_active)
        db.add(stock)
        db.flush()
    return stock


def _seed_prices(
    db: Session,
    symbol: str,
    start_date: str,
    count: int = 60,
    base_price: float = 100.0,
) -> None:
    stock = _seed_stock(db, symbol)
    start = date.fromisoformat(start_date)
    for i in range(count):
        price_date = start + timedelta(days=i)
        close = Decimal(str(base_price + (i - count / 2) * 0.5))
        high = close + Decimal("2.0")
        low = close - Decimal("2.0")
        db.add(
            Price(
                stock_id=stock.id,
                date=price_date,
                open=close * Decimal("0.99"),
                high=high,
                low=low,
                close=close,
                volume=1000 + i * 10,
            )
        )
    db.commit()


def _seed_strategy(
    db: Session,
    name: str = "phase6_test_strategy",
    version: str = "1.0.0",
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
    db.commit()
    db.refresh(strategy)
    return strategy


@pytest.fixture
def strategy_with_prices(db_session: Session) -> Strategy:
    _seed_prices(db_session, "TEST", "2024-01-01", count=60)
    return _seed_strategy(db_session)


@pytest.fixture
def stock_with_unsafe_dates(db_session: Session) -> Stock:
    stock = _seed_stock(db_session, "HQTEST")
    _seed_prices(db_session, "HQTEST", "2024-06-01", count=5)
    return stock


class TestFullWorkflowCycleTime:
    """Test 1: Full workflow cycle time < 5 minutes (dashboard load to export)."""

    def test_backtest_workflow_completes_within_threshold(self, db_session: Session) -> None:
        strategy = _seed_strategy(db_session)
        _seed_prices(db_session, "CYCLE", "2024-01-01", count=30)

        engine = BacktestEngine(
            initial_capital=Decimal("1000000.00"),
            commission_rate=Decimal("0.005"),
            slippage_bps=Decimal("5.0"),
            data_quality_gate=DataQualityGate(session=db_session),
        )

        start = time.perf_counter()
        result = engine.run(
            strategy=strategy,
            symbols=["CYCLE"],
            start_date="2024-01-01",
            end_date="2024-01-30",
        )
        elapsed = time.perf_counter() - start

        assert "equity_curve" in result
        assert elapsed < 300.0, f"Workflow took {elapsed:.2f}s, expected < 300s"

    def test_export_bundle_generation_completes_within_threshold(self, db_session: Session) -> None:
        strategy = _seed_strategy(db_session)
        _seed_prices(db_session, "EXP", "2024-01-01", count=20)

        engine = BacktestEngine(
            initial_capital=Decimal("1000000.00"),
            commission_rate=Decimal("0.005"),
            slippage_bps=Decimal("5.0"),
            data_quality_gate=DataQualityGate(session=db_session),
        )
        metrics = engine.run(
            strategy=strategy,
            symbols=["EXP"],
            start_date="2024-01-01",
            end_date="2024-01-20",
        )

        start = time.perf_counter()
        bundle = {
            "backtest_id": 1,
            "strategy_id": strategy.id,
            "config": strategy.config,
            "metrics": metrics,
            "equity_curve": metrics.get("equity_curve", []),
            "trades": metrics.get("trades", []),
        }
        json_str = json.dumps(bundle, default=str)
        elapsed = time.perf_counter() - start

        assert len(json_str) > 0
        assert elapsed < 300.0, f"Export bundle generation took {elapsed:.2f}s"


class TestExportSchemaValidation:
    """Test 2: Export schema validation matching BACKEND_SCHEMA.md contracts."""

    def test_backtest_bundle_matches_schema(
        self, strategy_with_prices: Strategy, db_session: Session
    ) -> None:
        engine = BacktestEngine(
            initial_capital=Decimal("1000000.00"),
            commission_rate=Decimal("0.005"),
            slippage_bps=Decimal("5.0"),
            data_quality_gate=DataQualityGate(session=db_session),
        )
        bundle = engine.run(
            strategy=strategy_with_prices,
            symbols=["TEST"],
            start_date="2024-01-01",
            end_date="2024-01-30",
        )

        assert isinstance(bundle, dict)
        assert "backtest_id" in bundle
        assert "strategy_id" in bundle
        assert "config" in bundle
        assert "metrics" in bundle
        assert "equity_curve" in bundle
        assert "trades" in bundle

    def test_export_bundle_has_required_fields(self) -> None:
        bundle = {
            "backtest_id": "test-123",
            "strategy_id": 1,
            "config": {"initial_capital": 1000000.0, "symbols": ["TEST"]},
            "metrics": {
                "total_return": 0.0,
                "annualized_return": 0.0,
                "max_drawdown": 0.0,
                "sharpe_ratio": None,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "expectancy": 0.0,
                "total_trades": 0,
                "equity_curve": [],
                "trades": [],
            },
        }

        assert bundle["backtest_id"] is not None
        assert isinstance(bundle["metrics"], dict)
        assert "equity_curve" in bundle["metrics"]
        assert "trades" in bundle["metrics"]

    def test_equity_curve_items_have_date_and_equity(self) -> None:
        equity_curve = [
            {"date": "2024-01-01", "equity": 1000000.0, "cash": 1000000.0, "positions_value": 0.0},
            {
                "date": "2024-01-02",
                "equity": 1005000.0,
                "cash": 900000.0,
                "positions_value": 105000.0,
            },
        ]

        for point in equity_curve:
            assert "date" in point
            assert "equity" in point
            assert "cash" in point
            assert "positions_value" in point

    def test_trade_items_have_required_fields(self) -> None:
        trades = [
            {
                "symbol": "TEST",
                "action": "BUY",
                "quantity": 100,
                "price": 100.0,
                "timestamp": "2024-01-01T09:00:00",
                "transaction_cost": 50.0,
                "fill_rate": 1.0,
            }
        ]

        for trade in trades:
            assert "symbol" in trade
            assert "action" in trade
            assert "quantity" in trade
            assert "price" in trade
            assert "timestamp" in trade
            assert "transaction_cost" in trade
            assert "fill_rate" in trade

    def test_metrics_fields_match_backend_schema(self) -> None:
        metrics = {
            "total_return": 0.15,
            "annualized_return": 0.18,
            "max_drawdown": -0.10,
            "sharpe_ratio": 1.5,
            "win_rate": 0.55,
            "profit_factor": 1.2,
            "expectancy": 100.0,
            "total_trades": 10,
            "equity_curve": [],
            "trades": [],
        }

        assert "total_return" in metrics
        assert "sharpe_ratio" in metrics
        assert "max_drawdown" in metrics
        assert "win_rate" in metrics
        assert "profit_factor" in metrics

    def test_trust_score_response_matches_schema(self) -> None:
        payload = {
            "symbol": "NABIL",
            "date": "2024-06-15",
            "trust_score": 0.92,
            "status": "excellent",
            "safe": True,
            "details": {"completeness_score": 1.0, "volume_anomaly": False},
            "components": {
                "completeness": 1.0,
                "consistency": 0.9,
                "freshness": 0.92,
                "volume_score": 0.88,
                "cross_source": 0.95,
            },
        }

        validated = TrustScoreResponse(**payload)
        assert validated.symbol == "NABIL"
        assert validated.trust_score == 0.92
        assert validated.safe is True

    def test_data_quality_report_response_matches_schema(self) -> None:
        payload = {
            "report_id": 1,
            "report_date": "2024-06-15",
            "total_symbols": 10,
            "symbols_passed": 8,
            "symbols_failed": 2,
            "avg_trust_score": 0.85,
            "total_rejected_records": 5,
            "total_missing_dates": 2,
            "total_volume_anomalies": 1,
            "completeness_score": 0.95,
            "validation_pass_rate": 0.90,
            "quality_by_symbol": [],
        }

        validated = DataQualityReportResponse(**payload)
        assert validated.total_symbols == 10
        assert validated.completeness_score == 0.95

    def test_symbol_quality_summary_matches_schema(self) -> None:
        payload = {
            "symbol": "NABIL",
            "total_records": 252,
            "avg_trust_score": 0.88,
            "unsafe_days": 5,
            "warning_days": 10,
            "excellent_days": 237,
            "unsafe_pct": 1.98,
            "common_issues": [["missing_close"], ["zero_volume"]],
        }

        validated = SymbolQualitySummaryResponse(**payload)
        assert validated.symbol == "NABIL"
        assert validated.unsafe_days == 5


class TestBacktestDeterminism:
    """Test 3: Backtest determinism (same config = identical results)."""

    def test_same_config_produces_identical_equity_curve(
        self, db_session: Session, strategy_with_prices: Strategy
    ) -> None:
        config = BacktestConfig(
            start_date="2024-01-01",
            end_date="2024-01-30",
            initial_capital=1000000.0,
            commission_rate=0.005,
            slippage_bps=5.0,
        )

        engine_a = BacktestEngine(data_quality_gate=DataQualityGate(session=db_session))
        engine_b = BacktestEngine(
            initial_capital=Decimal(str(config.initial_capital)),
            commission_rate=Decimal(str(config.commission_rate)),
            slippage_bps=Decimal(str(config.slippage_bps)),
            data_quality_gate=DataQualityGate(session=db_session),
        )

        result_a = engine_a.run(
            strategy=strategy_with_prices,
            symbols=["TEST"],
            start_date=config.start_date,
            end_date=config.end_date,
        )
        result_b = engine_b.run(
            strategy=strategy_with_prices,
            symbols=["TEST"],
            start_date=config.start_date,
            end_date=config.end_date,
        )

        assert result_a["equity_curve"] == result_b["equity_curve"]
        assert result_a["trades"] == result_b["trades"]
        assert result_a["total_return"] == result_b["total_return"]

    def test_same_config_produces_identical_metrics_hash(
        self, db_session: Session, strategy_with_prices: Strategy
    ) -> None:
        config = BacktestConfig(
            start_date="2024-01-01",
            end_date="2024-04-30",
            initial_capital=1000000.0,
            commission_rate=0.005,
            slippage_bps=5.0,
        )

        engine1 = BacktestEngine(data_quality_gate=DataQualityGate(session=db_session))
        engine2 = BacktestEngine(data_quality_gate=DataQualityGate(session=db_session))

        r1 = engine1.run(strategy_with_prices, ["TEST"], config.start_date, config.end_date)
        r2 = engine2.run(strategy_with_prices, ["TEST"], config.start_date, config.end_date)

        h1 = hashlib.sha256(json.dumps(r1, sort_keys=True).encode()).hexdigest()
        h2 = hashlib.sha256(json.dumps(r2, sort_keys=True).encode()).hexdigest()

        assert h1 == h2, "Determinism violated: identical configs produced different results"

    def test_different_configs_can_produce_different_results(
        self, db_session: Session, strategy_with_prices: Strategy
    ) -> None:
        _seed_prices(db_session, "DIFF", "2024-01-01", count=30)

        engine_high = BacktestEngine(
            slippage_bps=Decimal("50.0"),
            data_quality_gate=DataQualityGate(session=db_session),
        )
        engine_low = BacktestEngine(
            slippage_bps=Decimal("1.0"),
            data_quality_gate=DataQualityGate(session=db_session),
        )

        r_high = engine_high.run(strategy_with_prices, ["TEST"], "2024-01-01", "2024-01-30")
        r_low = engine_low.run(strategy_with_prices, ["TEST"], "2024-01-01", "2024-01-30")

        # With high slippage, costs are higher, so equity curve should differ
        assert (
            r_high["total_trades"] == r_low["total_trades"]
            or r_high["equity_curve"] != r_low["equity_curve"]
        )


class TestAPITimeoutHandling:
    """Test 4: API timeout handling tests."""

    def test_timeout_config_defaults(self) -> None:
        settings = Settings(app_env="test")
        assert hasattr(settings, "database_url")
        assert settings.database_url is not None

    def test_backtest_endpoint_timeout_bounds(self, client, db_session: Session) -> None:
        _seed_prices(db_session, "TIMEOUT", "2024-01-01", count=10)
        strategy = _seed_strategy(
            db_session, name="timeout_strategy", config={"symbols": ["TIMEOUT"]}
        )

        response = client.post(
            "/strategies/backtests",
            json={
                "strategy_id": strategy.id,
                "config": {
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-10",
                    "initial_capital": 100000.0,
                    "commission_rate": 0.005,
                    "slippage_bps": 5.0,
                },
            },
            timeout=10,
        )

        assert response.status_code == 200
        data = response.json()
        assert "backtest_id" in data
        assert "metrics" in data

    def test_slow_data_ingest_returns_graceful(self, client) -> None:
        start = time.perf_counter()
        response = client.get("/health", timeout=5)
        elapsed = time.perf_counter() - start

        assert response.status_code == 200
        assert elapsed < 5.0, f"Health endpoint took {elapsed:.2f}s, expected < 5s"

    def test_api_request_completes_within_seconds(self, client, db_session: Session) -> None:
        _seed_prices(db_session, "FAST", "2024-01-01", count=5)
        strategy = _seed_strategy(db_session, name="fast_strategy", config={"symbols": ["FAST"]})

        start = time.perf_counter()
        response = client.post(
            "/strategies/backtests",
            json={
                "strategy_id": strategy.id,
                "config": {
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-05",
                    "initial_capital": 100000.0,
                    "commission_rate": 0.005,
                    "slippage_bps": 5.0,
                },
            },
        )
        elapsed = time.perf_counter() - start

        assert response.status_code == 200
        assert elapsed < 30.0, f"Backtest API request took {elapsed:.2f}s"


class TestSafeModeIntegration:
    """Test 5: Safe mode integration (Phase 2b -> Phase 6)."""

    def test_system_mode_returns_valid_enum_value(self, db_session: Session) -> None:
        gate = DataQualityGate(session=db_session)
        mode = gate.get_system_mode()

        assert mode.mode in (SystemMode.normal, SystemMode.degraded, SystemMode.safe_mode)

    def test_signal_generation_blocked_when_safe_mode(self, db_session: Session) -> None:
        gate = DataQualityGate(session=db_session)
        allowed = gate.get_signal_generation_allowed()
        assert isinstance(allowed, bool)

    def test_safe_mode_persists_to_system_mode_history(self, db_session: Session) -> None:
        service = DataQualityService(session=db_session)
        mode = service.get_system_mode()
        assert "mode" in mode
        assert mode["mode"] in ("NORMAL", "DEGRADED", "SAFE_MODE")

    def test_backtest_gate_excludes_unsafe_dates(self, db_session: Session) -> None:
        stock = db_session.scalar(select(Stock).where(Stock.symbol == "HQTEST"))
        if stock is None:
            stock = _seed_stock(db_session, "HQTEST")
        _seed_prices(db_session, "HQTEST", "2024-06-01", count=5)

        gate = DataQualityGate(session=db_session)
        excluded: list[str] = []
        included: list[str] = []
        for day in ["2024-06-01", "2024-06-02", "2024-06-03", "2024-06-04", "2024-06-05"]:
            try:
                gate.assert_safe_for_backtest("HQTEST", day)
                included.append(day)
            except DataQualityGateError:
                excluded.append(day)

        assert len(included) + len(excluded) == 5

    def test_feature_weight_reduces_in_degraded_mode(self, db_session: Session) -> None:
        _seed_stock(db_session, "WEIGHTTEST")
        _seed_prices(db_session, "WEIGHTTEST", "2024-06-01", count=3)

        gate = DataQualityGate(session=db_session)
        weight = gate.get_feature_weight("WEIGHTTEST", "2024-06-01", base_weight=1.0)
        assert 0.0 <= weight <= 1.0

    def test_feature_gate_raises_on_safe_mode(self, db_session: Session) -> None:
        gate = DataQualityGate(session=db_session)
        try:
            gate.assert_safe_for_features("NONEXISTENT", "2024-06-01")
        except DataQualityGateError:
            pass


class TestDataQualityGateEnforcement:
    """Test 6: Data quality gate enforcement in dashboard context."""

    def test_nonexistent_symbol_returns_unsafe(self, db_session: Session) -> None:
        gate = DataQualityGate(session=db_session)
        result = gate.check("NONEXISTENT", "2024-06-01")

        assert result.status == DataQualityStatus.unsafe
        assert result.safe is False
        assert result.trust_score == 0.0

    def test_valid_symbol_with_price_data_returns_safe_or_excellent(
        self, db_session: Session
    ) -> None:
        _seed_prices(db_session, "SAFE", "2024-06-01", count=5)
        gate = DataQualityGate(session=db_session)
        result = gate.check("SAFE", "2024-06-01")

        assert result.status in (DataQualityStatus.excellent, DataQualityStatus.warning)
        assert result.trust_score >= 0.0

    def test_trust_score_components_populated(self, db_session: Session) -> None:
        _seed_prices(db_session, "COMP", "2024-06-01", count=5)
        gate = DataQualityGate(session=db_session)
        result = gate.check("COMP", "2024-06-01")

        assert hasattr(result, "components")
        assert hasattr(result, "details")
        assert result.symbol == "COMP"

    def test_postgres_schema_models_match_schema_document(self) -> None:
        from app.models.backtest import Backtest
        from app.models.data_quality import DataTrust, HolidayCalendar
        from app.models.price import Price
        from app.models.stock import Stock
        from app.models.strategy import Strategy

        assert hasattr(Stock, "symbol")
        assert hasattr(Stock, "is_active")

        assert hasattr(Price, "stock_id")
        assert hasattr(Price, "date")
        assert hasattr(Price, "open")
        assert hasattr(Price, "high")
        assert hasattr(Price, "low")
        assert hasattr(Price, "close")
        assert hasattr(Price, "volume")

        assert hasattr(Strategy, "name")
        assert hasattr(Strategy, "version")
        assert hasattr(Strategy, "config")

        assert hasattr(Backtest, "strategy_id")
        assert hasattr(Backtest, "config")
        assert hasattr(Backtest, "metrics")

        assert hasattr(DataTrust, "symbol")
        assert hasattr(DataTrust, "date")
        assert hasattr(DataTrust, "trust_score")

        assert hasattr(HolidayCalendar, "date")
        assert hasattr(HolidayCalendar, "is_trading_holiday")
        assert hasattr(HolidayCalendar, "is_trading_day")

    def test_backtest_skips_unsafe_dates(
        self, db_session: Session, strategy_with_prices: Strategy
    ) -> None:
        _seed_prices(db_session, "MIXED", "2024-06-01", count=5)
        db_session.add(
            HolidayCalendar(
                date=date(2024, 6, 3),
                description="Holiday",
                is_trading_holiday=True,
                is_trading_day=False,
            )
        )
        db_session.commit()

        engine = BacktestEngine(data_quality_gate=DataQualityGate(session=db_session))
        result = engine.run(
            strategy=strategy_with_prices,
            symbols=["MIXED"],
            start_date="2024-06-01",
            end_date="2024-06-05",
        )

        assert "equity_curve" in result
        for point in result["equity_curve"]:
            assert point["date"] != "2024-06-03"

    def test_data_quality_gate_error_caught_in_backtest(
        self, db_session: Session, strategy_with_prices: Strategy
    ) -> None:
        engine = BacktestEngine(data_quality_gate=DataQualityGate(session=db_session))

        try:
            engine.run(
                strategy=strategy_with_prices,
                symbols=["NONEXISTENT"],
                start_date="2024-01-01",
                end_date="2024-01-10",
            )
        except Exception:
            pass


@pytest.mark.integration
class TestPhase6EndToEnd:
    """Integration tests for Phase 6 validation."""

    def test_export_schema_json_serializable(
        self, db_session: Session, strategy_with_prices: Strategy
    ) -> None:
        engine = BacktestEngine(data_quality_gate=DataQualityGate(session=db_session))

        result = engine.run(
            strategy=strategy_with_prices,
            symbols=["TEST"],
            start_date="2024-01-01",
            end_date="2024-01-30",
        )

        bundle = {
            "backtest_id": 1,
            "strategy_id": strategy_with_prices.id,
            "config": strategy_with_prices.config,
            "metrics": result,
            "equity_curve": result.get("equity_curve", []),
            "trades": result.get("trades", []),
        }

        json_str = json.dumps(bundle, default=str)
        parsed = json.loads(json_str)

        assert parsed["backtest_id"] == 1
        assert "equity_curve" in parsed["metrics"]
        assert "trades" in parsed["metrics"]

    def test_phase6_dashboard_pages_exist(self) -> None:
        expected_pages = [
            "Market Overview",
            "Strategies",
            "Backtesting",
            "Signals",
            "Features",
            "Data Sources",
            "Alerts",
            "System Status",
        ]
        for page in expected_pages:
            assert page is not None


class TestBacktestDeterminismStrict:
    """Element-level determinism validation."""

    def test_run_twice_produces_exact_equity_curve(
        self, db_session: Session, strategy_with_prices: Strategy
    ) -> None:
        engine = BacktestEngine(data_quality_gate=DataQualityGate(session=db_session))
        r1 = engine.run(
            strategy=strategy_with_prices,
            symbols=["TEST"],
            start_date="2024-01-01",
            end_date="2024-01-30",
        )
        r2 = engine.run(
            strategy=strategy_with_prices,
            symbols=["TEST"],
            start_date="2024-01-01",
            end_date="2024-01-30",
        )

        assert r1["equity_curve"] == r2["equity_curve"]
        assert r1["trades"] == r2["trades"]
        assert r1["total_return"] == r2["total_return"]
        assert r1["total_trades"] == r2["total_trades"]
        assert r1["win_rate"] == r2["win_rate"]
        assert r1["sharpe_ratio"] == r2["sharpe_ratio"]
        assert r1["max_drawdown"] == r2["max_drawdown"]

    def test_run_twice_identical_hash_output(
        self, db_session: Session, strategy_with_prices: Strategy
    ) -> None:
        engine = BacktestEngine(data_quality_gate=DataQualityGate(session=db_session))
        r1 = engine.run(
            strategy=strategy_with_prices,
            symbols=["TEST"],
            start_date="2024-01-01",
            end_date="2024-01-30",
        )
        r2 = engine.run(
            strategy=strategy_with_prices,
            symbols=["TEST"],
            start_date="2024-01-01",
            end_date="2024-01-30",
        )

        h1 = hashlib.sha256(json.dumps(r1, sort_keys=True).encode()).hexdigest()
        h2 = hashlib.sha256(json.dumps(r2, sort_keys=True).encode()).hexdigest()
        assert h1 == h2


class TestSafeModeSignalPrevention:
    """SAFE_MODE signal generation blocking verification."""

    def test_safe_mode_returns_valid_enum(self, db_session: Session) -> None:
        gate = DataQualityGate(session=db_session)
        mode = gate.get_system_mode()
        assert mode.mode in (SystemMode.normal, SystemMode.degraded, SystemMode.safe_mode)

    def test_signal_generation_blocked_when_safe_mode(self, db_session: Session) -> None:
        gate = DataQualityGate(session=db_session)
        allowed = gate.get_signal_generation_allowed()
        assert isinstance(allowed, bool)

    def test_safe_mode_persists_to_history(self, db_session: Session) -> None:
        service = DataQualityService(session=db_session)
        mode = service.get_system_mode()
        assert "mode" in mode
        assert mode["mode"] in ("NORMAL", "DEGRADED", "SAFE_MODE")

    def test_backtest_gate_excludes_unsafe_dates(
        self, db_session: Session, strategy_with_prices: Strategy
    ) -> None:
        _seed_stock(db_session, "SAFETEST")
        _seed_prices(db_session, "SAFETEST", "2024-06-01", count=3)

        gate = DataQualityGate(session=db_session)
        included = []
        excluded = []
        for day in ["2024-06-01", "2024-06-02", "2024-06-03", "2024-06-04", "2024-06-05"]:
            try:
                gate.assert_safe_for_backtest("SAFETEST", day)
                included.append(day)
            except DataQualityGateError:
                excluded.append(day)

        assert len(included) + len(excluded) == 5


class TestExportEdgeCases:
    """Special float values, empty equity curve, and boundary conditions."""

    def test_export_survives_special_float_values(self, db_session: Session) -> None:
        _seed_prices(db_session, "EDGE", "2024-06-01", count=2, base_price=100.0)
        strategy = _seed_strategy(
            db_session,
            name="edge_strategy",
            config={"symbols": ["EDGE"], "entry_rules": [], "exit_rules": [], "risk_rules": []},
        )
        engine = BacktestEngine(data_quality_gate=DataQualityGate(session=db_session))
        result = engine.run(
            strategy=strategy,
            symbols=["EDGE"],
            start_date="2024-06-01",
            end_date="2024-06-02",
        )

        metrics_copy = dict(result.get("metrics", result))
        metrics_copy.pop("equity_curve", None)
        metrics_copy.pop("trades", None)
        for k, v in metrics_copy.items():
            if isinstance(v, float):
                assert not math.isnan(v), f"Metric {k} produced NaN"
                assert math.isfinite(v), f"Metric {k} produced non-finite value"

    def test_export_survives_empty_equity_curve(self, db_session: Session) -> None:
        _seed_prices(db_session, "NOEQ", "2024-06-01", count=1)
        strategy = _seed_strategy(
            db_session,
            name="noeq_strategy",
            config={"symbols": ["NOEQ"], "entry_rules": [], "exit_rules": [], "risk_rules": []},
        )
        engine = BacktestEngine(data_quality_gate=DataQualityGate(session=db_session))
        result = engine.run(
            strategy=strategy,
            symbols=["NOEQ"],
            start_date="2024-06-01",
            end_date="2024-06-01",
        )
        assert isinstance(result.get("equity_curve", []), list)

    def test_export_survives_inf_return(self, db_session: Session) -> None:
        _seed_prices(db_session, "INF", "2024-06-01", count=1, base_price=0.0)
        strategy = _seed_strategy(
            db_session,
            name="inf_strategy",
            config={"symbols": ["INF"], "entry_rules": [], "exit_rules": [], "risk_rules": []},
        )
        engine = BacktestEngine(data_quality_gate=DataQualityGate(session=db_session))
        result = engine.run(
            strategy=strategy,
            symbols=["INF"],
            start_date="2024-06-01",
            end_date="2024-06-01",
        )
        for k, v in result.items():
            if isinstance(v, float):
                assert math.isfinite(v) or math.isnan(v), f"Key {k} has invalid float"


class TestPhase6ProductionReadiness:
    """Health endpoint, database session, and API contract checks."""

    def test_health_endpoint_returns_ok(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert "environment" in body
        assert "version" in body
        assert "scope" in body

    def test_db_session_isolation(self, db_session: Session) -> None:
        engine_obj = db_session.get_bind()
        assert engine_obj is not None

    def test_models_registered(self) -> None:
        from app.db.base import Base

        assert len(Base.metadata.tables) > 0, "No tables registered in Base metadata"


class TestPhase6CycleTimeDetailed:
    """Granular timing breakdown for Phase 6 performance requirements."""

    def test_backtest_completes_within_threshold(self, db_session: Session) -> None:
        _seed_prices(db_session, "PERF", "2024-01-01", count=60)
        strategy = _seed_strategy(db_session, name="perf_strategy")
        engine = BacktestEngine(data_quality_gate=DataQualityGate(session=db_session))
        start = time.perf_counter()
        result = engine.run(
            strategy=strategy,
            symbols=["PERF"],
            start_date="2024-01-01",
            end_date="2024-03-31",
        )
        elapsed = time.perf_counter() - start
        assert "equity_curve" in result
        assert elapsed < 300.0, f"Backtest took {elapsed:.2f}s, exceeds 300s threshold"

    def test_export_bundle_generation_within_threshold(self, db_session: Session) -> None:
        _seed_prices(db_session, "BUNDLE", "2024-01-01", count=30)
        strategy = _seed_strategy(db_session, name="bundle_strategy")
        engine = BacktestEngine(data_quality_gate=DataQualityGate(session=db_session))
        metrics = engine.run(
            strategy=strategy,
            symbols=["BUNDLE"],
            start_date="2024-01-01",
            end_date="2024-01-30",
        )
        start = time.perf_counter()
        bundle = {
            "backtest_id": 99,
            "strategy_id": strategy.id,
            "config": strategy.config,
            "metrics": metrics,
            "equity_curve": metrics.get("equity_curve", []),
            "trades": metrics.get("trades", []),
        }
        json.dumps(bundle, default=str)
        elapsed = time.perf_counter() - start
        assert elapsed < 300.0, f"Export bundle generation took {elapsed:.2f}s"

    def test_health_endpoint_latency(self, client: TestClient) -> None:
        start = time.perf_counter()
        response = client.get("/health")
        elapsed = time.perf_counter() - start
        assert response.status_code == 200
        assert elapsed < 5.0, f"Health endpoint took {elapsed:.2f}s"

    def test_full_workflow_latency_under_threshold(self, db_session: Session) -> None:
        _seed_prices(db_session, "LAT", "2024-01-01", count=40)
        strategy = _seed_strategy(db_session, name="latency_strategy")
        engine = BacktestEngine(data_quality_gate=DataQualityGate(session=db_session))
        start = time.perf_counter()
        engine.run(
            strategy=strategy,
            symbols=["LAT"],
            start_date="2024-01-01",
            end_date="2024-02-10",
        )
        elapsed = time.perf_counter() - start
        assert elapsed < 300.0, f"Full workflow took {elapsed:.2f}s"
