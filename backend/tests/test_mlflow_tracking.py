from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import app.models  # noqa: F401
from app.models.backtest import Backtest
from app.models.price import Price
from app.models.stock import Stock
from app.models.strategy import Strategy
from app.services import mlflow_tracking as mlflow_tracking_module
from app.services.backtest import BacktestService
from app.services.mlflow_tracking import (
    MLflowTrackingService,
    evaluate_promotion_gate,
    mlflow_tracker,
)
from sqlalchemy.orm import Session, sessionmaker


class FakeRunInfo:
    run_id = "run-123"


class FakeRun:
    info = FakeRunInfo()

    def __enter__(self) -> FakeRun:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None


class FakeExperiment:
    experiment_id = "exp-123"


class FakeMLflow:
    def __init__(self) -> None:
        self.tracking_uri: str | None = None
        self.experiments: dict[str, FakeExperiment] = {}
        self.runs: list[dict[str, object]] = []
        self.params: dict[str, str] = {}
        self.metrics: dict[str, float] = {}
        self.artifacts: list[dict[str, str]] = []
        self.current_run = FakeRun()

    def set_tracking_uri(self, uri: str) -> None:
        self.tracking_uri = uri

    def get_experiment_by_name(self, name: str) -> FakeExperiment | None:
        return self.experiments.get(name)

    def create_experiment(self, name: str) -> str:
        experiment = FakeExperiment()
        self.experiments[name] = experiment
        return experiment.experiment_id

    def start_run(self, experiment_id: str, run_name: str) -> FakeRun:
        self.runs.append({"experiment_id": experiment_id, "run_name": run_name})
        return self.current_run

    def log_params(self, params: dict[str, str]) -> None:
        self.params = params

    def log_metrics(self, metrics: dict[str, float]) -> None:
        self.metrics = metrics

    def log_artifact(self, path: str, artifact_path: str | None = None) -> None:
        self.artifacts.append({"artifact_path": path, "artifact_path_name": artifact_path or ""})

    def log_artifacts(self, artifact_dir: str, artifact_path: str | None = None) -> None:
        self.artifacts.append(
            {"artifact_path": artifact_dir, "artifact_path_name": artifact_path or ""}
        )


def _install_fake_mlflow(monkeypatch) -> FakeMLflow:
    fake_mlflow = FakeMLflow()
    monkeypatch.setattr("app.services.mlflow_tracking.mlflow", fake_mlflow)
    return fake_mlflow


def test_log_backtest_disabled_without_mlflow(monkeypatch) -> None:
    monkeypatch.setattr("app.services.mlflow_tracking.mlflow", None)

    result = mlflow_tracker.log_backtest(
        backtest_id=1,
        strategy_id=1,
        strategy_name="test_strategy",
        strategy_version="v1.0.0",
        config={"start_date": "2024-01-01", "end_date": "2024-01-31"},
        metrics={"total_return": 0.01},
        strategy_config={"entry_rules": [], "exit_rules": [], "risk_rules": []},
        symbol_count=1,
    )

    assert result.enabled is False
    assert result.status == "disabled"
    assert result.error == "MLflow is not installed"


def test_log_backtest_success_with_mock_mlflow(tmp_path, monkeypatch) -> None:
    fake_mlflow = _install_fake_mlflow(monkeypatch)
    service = MLflowTrackingService(
        tracking_uri=f"file:{tmp_path}",
        enabled=True,
        experiment_prefix="nepse",
    )

    result = service.log_backtest(
        backtest_id=42,
        strategy_id=7,
        strategy_name="momentum",
        strategy_version="v1.2.0",
        config={
            "start_date": "2024-01-01",
            "end_date": "2024-03-31",
            "initial_capital": 100000.0,
            "commission_rate": 0.005,
            "slippage_bps": 5.0,
        },
        metrics={
            "total_return": 0.05,
            "annualized_return": 0.2,
            "max_drawdown": 0.03,
            "sharpe_ratio": 1.4,
            "win_rate": 0.55,
            "profit_factor": 1.2,
            "expectancy": 150.0,
            "total_trades": 10,
            "equity_curve": [{"date": "2024-01-01", "equity": 100000.0}],
            "trades": [
                {
                    "symbol": "TEST",
                    "action": "BUY",
                    "quantity": 10,
                    "price": 100.0,
                    "timestamp": "2024-01-01T09:00:00",
                    "transaction_cost": 5.0,
                    "fill_rate": 1.0,
                }
            ],
        },
        strategy_config={
            "entry_rules": [{"rule": "rsi_oversold"}],
            "exit_rules": [{"rule": "rsi_exit_long"}],
            "risk_rules": [{"rule": "max_position_size"}],
        },
        symbol_count=1,
    )

    assert result == mlflow_tracking_module.MLflowRunResult(
        enabled=True,
        experiment_name="nepse/phase_2b_baseline",
        run_id="run-123",
        status="logged",
    )
    assert fake_mlflow.tracking_uri == f"file:{tmp_path}"
    assert fake_mlflow.runs == [{"experiment_id": "exp-123", "run_name": "backtest_42"}]
    assert fake_mlflow.params["strategy_id"] == "7"
    assert fake_mlflow.params["strategy_name"] == "momentum"
    assert fake_mlflow.params["entry_rule_count"] == "1"
    assert fake_mlflow.metrics["total_return"] == 0.05
    assert fake_mlflow.artifacts[0]["artifact_path_name"] == "backtest"


def test_log_backtest_disabled_by_config(monkeypatch) -> None:
    fake_mlflow = _install_fake_mlflow(monkeypatch)
    service = MLflowTrackingService(enabled=False)

    result = service.log_backtest(
        backtest_id=1,
        strategy_id=1,
        strategy_name="disabled",
        strategy_version="v1.0.0",
        config={},
        metrics={},
        strategy_config={},
    )

    assert result.enabled is False
    assert result.status == "disabled"
    assert result.error == "MLflow is disabled"
    assert fake_mlflow.tracking_uri is None


def test_log_model_training_success_with_mock_mlflow(tmp_path, monkeypatch) -> None:
    fake_mlflow = _install_fake_mlflow(monkeypatch)
    model_path = tmp_path / "logistic_v1.joblib"
    model_path.write_text("fake model", encoding="utf-8")
    service = MLflowTrackingService(
        tracking_uri=f"file:{tmp_path}",
        enabled=True,
        experiment_prefix="nepse",
    )

    result = service.log_model_training(
        model_name="logistic",
        model_version="v1.0.0",
        feature_version="v4.0.0",
        symbol="TEST",
        split_sizes={"train_size": 70, "val_size": 15, "test_size": 15},
        metrics={"val_accuracy": 0.82, "sharpe_ratio": 0.9},
        params={"max_iter": 1000},
        model_path=model_path,
    )

    assert result.enabled is True
    assert result.status == "logged"
    assert result.run_id == "run-123"
    assert fake_mlflow.runs == [{"experiment_id": "exp-123", "run_name": "logistic_v1.0.0"}]
    assert fake_mlflow.params["model_name"] == "logistic"
    assert fake_mlflow.params["feature_version"] == "v4.0.0"
    assert fake_mlflow.params["train_size"] == 70
    assert fake_mlflow.params["max_iter"] == "1000"
    assert fake_mlflow.metrics["val_accuracy"] == 0.82
    assert fake_mlflow.artifacts[0]["artifact_path_name"] == "model"


def test_promotion_gate_compares_higher_and_lower_is_better() -> None:
    candidate = {
        "total_return": 0.12,
        "sharpe_ratio": 1.2,
        "max_drawdown": 0.08,
    }
    benchmark = {
        "total_return": 0.10,
        "sharpe_ratio": 1.3,
        "max_drawdown": 0.10,
    }
    baselines = {
        "previous_model": {
            "total_return": 0.11,
            "sharpe_ratio": 1.3,
            "max_drawdown": 0.07,
        }
    }

    result = evaluate_promotion_gate(
        candidate_metrics=candidate,
        benchmark_metrics=benchmark,
        baseline_metrics=baselines,
        required_metrics=["total_return", "sharpe_ratio", "max_drawdown"],
    )

    assert result.benchmark == {
        "total_return": True,
        "sharpe_ratio": False,
        "max_drawdown": True,
    }
    assert result.baselines["previous_model"] == {
        "total_return": True,
        "sharpe_ratio": False,
        "max_drawdown": False,
    }
    assert result.promotable is False


def _seed_backtest_data(db: Session) -> Strategy:
    stock = Stock(symbol="TEST", is_active=True)
    db.add(stock)
    db.flush()

    start = date(2024, 1, 1)
    for index in range(60):
        close = 100.0 + index * 0.25
        db.add(
            Price(
                stock_id=stock.id,
                date=start + timedelta(days=index),
                open=Decimal(str(close * 0.99)),
                high=Decimal(str(close + 1.0)),
                low=Decimal(str(close - 1.0)),
                close=Decimal(str(close)),
                volume=1000 + index,
            )
        )

    strategy = Strategy(
        name="mlflow_disabled_strategy",
        version="v1.0.0",
        config={
            "symbols": ["TEST"],
            "entry_rules": [],
            "exit_rules": [],
            "risk_rules": [],
        },
    )
    db.add(strategy)
    db.commit()
    db.refresh(strategy)
    return strategy


def test_backtest_service_ignores_unavailable_mlflow_logging(
    db_session: Session,
    monkeypatch,
) -> None:
    engine = db_session.get_bind()
    TestSessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        class_=Session,
    )
    monkeypatch.setattr("app.services.backtest.SessionLocal", TestSessionLocal)

    def raise_mlflow_error(*args: object, **kwargs: object) -> None:
        raise RuntimeError("mlflow unavailable")

    monkeypatch.setattr(mlflow_tracking_module.mlflow_tracker, "log_backtest", raise_mlflow_error)

    strategy = _seed_backtest_data(db_session)
    service = BacktestService(session=db_session)

    result = service.run_backtest(
        strategy_id=strategy.id,
        config={
            "start_date": "2024-01-01",
            "end_date": "2024-02-29",
            "initial_capital": 100000.0,
            "commission_rate": 0.005,
            "slippage_bps": 5.0,
        },
    )

    assert result["strategy_id"] == strategy.id
    assert result["backtest_id"] is not None
    backtest = db_session.get(Backtest, result["backtest_id"])
    assert backtest is not None
    assert backtest.metrics["total_trades"] == 0
