"""Tests for Phase 5 ML training pipeline."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import app.models  # noqa: F401
import numpy as np
import pytest
from app.models.model_registry import ModelRegistry
from app.models.price import Price
from app.models.stock import Stock
from app.services.feature import (
    FEATURE_REGISTRY,
    FEATURE_VERSION,
    FeatureService,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from ml.dataset import DatasetBuilder, DatasetBundle
from ml.drift_monitoring import CorrelationMonitor, DriftMonitor
from ml.evaluation import ModelEvaluator
from ml.experiment_tracking import ExperimentTracker
from ml.feature_vector import (
    FEATURE_DIM,
    FEATURE_ORDER,
    build_feature_vector,
    fill_missing,
    validate_vector,
)
from ml.labeling import LabelConfig, LabelMode, create_labels
from ml.position_sizing import PositionSizer, SizingMethod
from ml.risk_manager import RiskManager, StopLossManager
from ml.training import ModelTrainer


def _seed_price_series(
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
        close = base_price + (i - count / 2) * 0.5 + np.random.randn() * 2
        high = close + abs(np.random.randn()) * 1
        low = close - abs(np.random.randn()) * 1
        db.add(
            Price(
                stock_id=stock.id,
                date=price_date,
                open=Decimal(str(max(1.0, close * 0.99))),
                high=Decimal(str(high)),
                low=Decimal(str(low)),
                close=Decimal(str(close)),
                volume=int(1000 + abs(np.random.randn()) * 500),
            )
        )
    db.commit()
    return stock.id


def _seed_features(db: Session, symbol: str) -> None:
    service = FeatureService(session=db)
    service.compute_features_batch(symbol)


class TestFeatureVector:
    def test_feature_order_matches_registry(self) -> None:
        assert FEATURE_ORDER == list(FEATURE_REGISTRY.keys())

    def test_feature_dim(self) -> None:
        assert FEATURE_DIM == len(FEATURE_REGISTRY)

    def test_build_vector_full(self) -> None:
        values = {name: float(i + 1) for i, name in enumerate(FEATURE_ORDER)}
        vector = build_feature_vector(values)
        assert vector.shape == (FEATURE_DIM,)
        for i, name in enumerate(FEATURE_ORDER):
            assert abs(vector[i] - values[name]) < 1e-9

    def test_build_vector_missing_zeros(self) -> None:
        values = {"rsi_14": 75.0}
        vector = build_feature_vector(values)
        assert vector.shape == (FEATURE_DIM,)
        assert abs(vector[0] - 75.0) < 1e-9
        assert abs(vector[1]) < 1e-9

    def test_build_vector_none_missing(self) -> None:
        values = {"rsi_14": None, "sma_20": 100.0}
        vector = build_feature_vector(values)
        assert abs(vector[FEATURE_ORDER.index("rsi_14")]) < 1e-9
        assert abs(vector[FEATURE_ORDER.index("sma_20")] - 100.0) < 1e-9

    def test_validate_vector_ok(self) -> None:
        vector = np.zeros(FEATURE_DIM, dtype=np.float64)
        out = validate_vector(vector)
        assert out is vector

    def test_validate_vector_wrong_length(self) -> None:
        with pytest.raises(ValueError):
            validate_vector(np.zeros(FEATURE_DIM + 1, dtype=np.float64))

    def test_fill_missing(self) -> None:
        vector = np.array([0.0, np.nan, np.inf, 1.0], dtype=np.float64)
        out = fill_missing(vector, fill_value=5.0)
        assert abs(out[1] - 5.0) < 1e-9
        assert abs(out[2] - 5.0) < 1e-9
        assert abs(out[3] - 1.0) < 1e-9


class TestLabeling:
    def test_classification_labels_up(self) -> None:
        prices = np.linspace(100.0, 110.0, 20)
        y, returns, valid = create_labels(prices, LabelConfig(horizon=1, up_threshold=0.0))
        assert y[0] == 1.0

    def test_classification_labels_down(self) -> None:
        prices = np.linspace(110.0, 100.0, 20)
        y, returns, valid = create_labels(prices, LabelConfig(horizon=1, down_threshold=0.0))
        assert y[0] == -1.0

    def test_regression_mode(self) -> None:
        prices = np.linspace(100.0, 110.0, 20)
        y, returns, valid = create_labels(prices, LabelConfig(mode=LabelMode.regression))
        assert abs(y[0] - returns[0]) < 1e-9

    def test_horizon_nan_tail(self) -> None:
        prices = np.linspace(100.0, 110.0, 20)
        y, returns, valid = create_labels(prices, LabelConfig(horizon=5))
        assert np.all(~np.isnan(y))
        assert np.all(valid[:15])
        assert not np.all(valid[15:])


class TestDatasetBuilder:
    def test_build_raises_for_missing_stock(self, db_session: Session) -> None:
        builder = DatasetBuilder(session=db_session, feature_version=FEATURE_VERSION)
        with pytest.raises(ValueError):
            builder.build("MISSING")

    def test_build_returns_bundle(self, db_session: Session) -> None:
        _seed_price_series(db_session, "DATASET", "2024-01-01", count=40)
        _seed_features(db_session, "DATASET")
        builder = DatasetBuilder(session=db_session, feature_version=FEATURE_VERSION)
        bundle = builder.build("DATASET")
        assert isinstance(bundle, DatasetBundle)
        assert bundle.symbol == "DATASET"
        assert bundle.X_train.shape[1] == FEATURE_DIM
        assert bundle.X_train.shape[0] + bundle.X_val.shape[0] + bundle.X_test.shape[0] == len(
            bundle.train_dates
        ) + len(bundle.val_dates) + len(bundle.test_dates)

    def test_bundle_shapes_align(self, db_session: Session) -> None:
        _seed_price_series(db_session, "SHAPES", "2024-01-01", count=40)
        _seed_features(db_session, "SHAPES")
        builder = DatasetBuilder(session=db_session, feature_version=FEATURE_VERSION)
        bundle = builder.build("SHAPES")
        assert bundle.X_train.shape[0] == bundle.y_train.shape[0]
        assert bundle.X_val.shape[0] == bundle.y_val.shape[0]
        assert bundle.X_test.shape[0] == bundle.y_test.shape[0]


class TestModelTrainer:
    def test_train_logistic_persists(self, db_session: Session) -> None:
        _seed_price_series(db_session, "TRAIN", "2024-01-01", count=40)
        _seed_features(db_session, "TRAIN")
        builder = DatasetBuilder(session=db_session, feature_version=FEATURE_VERSION)
        bundle = builder.build("TRAIN")
        trainer = ModelTrainer(session=db_session, model_version="test.1.0")
        result = trainer.train_logistic(bundle, model_name="logistic")
        assert result.model_path.endswith(".joblib")
        assert result.model_version == "vtest.1.0"
        assert result.model_path is not None
        registry = db_session.scalar(select(ModelRegistry).where(ModelRegistry.name == "logistic"))
        assert registry is not None
        assert registry.metrics is not None
        assert "val_accuracy" in registry.metrics


class TestModelEvaluator:
    def test_evaluate_classification(self, db_session: Session) -> None:
        from sklearn.linear_model import LogisticRegression

        _seed_price_series(db_session, "EVAL", "2024-01-01", count=40)
        _seed_features(db_session, "EVAL")
        builder = DatasetBuilder(session=db_session, feature_version=FEATURE_VERSION)
        bundle = builder.build("EVAL")
        model = LogisticRegression(max_iter=1000)
        model.fit(bundle.X_train, bundle.y_train)
        evaluator = ModelEvaluator(session=db_session)
        metrics = evaluator.evaluate_classification(model, bundle.X_test, bundle.y_test)
        assert "accuracy" in metrics
        assert "f1_weighted" in metrics
        assert 0.0 <= metrics["accuracy"] <= 1.0


class TestWalkForward:
    def test_walk_forward_iterator(self, db_session: Session) -> None:
        _seed_price_series(db_session, "WALK", "2024-01-01", count=60)
        _seed_features(db_session, "WALK")
        builder = DatasetBuilder(session=db_session, feature_version=FEATURE_VERSION)
        windows = list(builder.walk_forward("WALK", window_size=0.5, step_size=0.25))
        assert len(windows) >= 1
        for wf in windows:
            assert wf.bundle.X_train.shape[1] == FEATURE_DIM

    def test_walk_forward_shapes(self, db_session: Session) -> None:
        _seed_price_series(db_session, "WALK_SHAPES", "2024-01-01", count=100)
        _seed_features(db_session, "WALK_SHAPES")
        builder = DatasetBuilder(session=db_session, feature_version=FEATURE_VERSION)
        windows = list(builder.walk_forward("WALK_SHAPES"))
        for wf in windows:
            assert wf.bundle.X_train.shape[0] + wf.bundle.X_val.shape[0] + wf.bundle.X_test.shape[
                0
            ] == len(wf.bundle.train_dates) + len(wf.bundle.val_dates) + len(wf.bundle.test_dates)


class TestPositionSizing:
    def test_fixed_sizing(self) -> None:
        sizer = PositionSizer(capital=100000, method=SizingMethod.fixed)
        result = sizer.calculate(price=100, confidence=0.8, volatility=0.02)
        assert result.quantity == 100
        assert result.sizing_method == "fixed"

    def test_confidence_sizing(self) -> None:
        sizer = PositionSizer(capital=100000, method=SizingMethod.confidence)
        result = sizer.calculate(price=100, confidence=0.5, volatility=0.02)
        assert result.quantity == 50

    def test_hybrid_sizing(self) -> None:
        sizer = PositionSizer(capital=100000, method=SizingMethod.hybrid)
        result = sizer.calculate(price=100, confidence=0.8, volatility=0.05)
        assert result.quantity > 0


class TestRiskManagement:
    def test_risk_manager_allow(self) -> None:
        rm = RiskManager(max_drawdown=0.3)
        decision = rm.check_trade("TEST", 5000, 100000, {})
        assert decision.allow_trade is True

    def test_risk_manager_drawdown(self) -> None:
        rm = RiskManager(max_drawdown=0.1)
        rm.evaluate("TEST", 100000, {})  # Set peak equity
        decision = rm.check_trade("TEST", 1000, 90000, {})  # 10% drawdown from 100k
        assert decision.allow_trade is False
        assert decision.reason is not None and "drawdown" in decision.reason

    def test_stop_loss_manager(self) -> None:
        slm = StopLossManager()
        slm.set_entry("TEST", 100.0)
        assert slm.check_exit("TEST", 94.0) == "stop_loss"
        assert slm.check_exit("TEST", 112.0) == "take_profit"
        assert slm.check_exit("TEST", 100.0) is None


class TestDriftMonitoring:
    def test_drift_detection_no_drift(self) -> None:
        dm = DriftMonitor(p_threshold=0.05, psi_threshold=0.2)
        ref = {"feature": np.array([1.0, 2.0, 3.0, 4.0, 5.0] * 20)}
        cur = {"feature": np.array([1.0, 2.0, 3.0, 4.0, 5.0] * 20)}
        results = dm.detect(ref, cur)
        assert all(not r.is_drift for r in results)

    def test_correlation_monitor(self) -> None:
        cm = CorrelationMonitor(threshold=0.8)
        ref = np.array([[1, 2], [3, 4], [5, 6], [7, 8]])
        cur = np.array([[1, 2], [3, 4], [5, 6], [7, 8]])
        result = cm.detect(ref, cur)
        assert result.get("significant_change") is False


class TestExperimentTracking:
    def test_log_experiment(self, tmp_path: Path) -> None:
        et = ExperimentTracker(experiments_dir=tmp_path)
        exp_id = et.log(
            strategy_version="v1.0",
            model_version="logistic_v1",
            dataset_version="dataset_v1",
            metrics={"sharpe": 1.5},
            config={"horizon": 5},
        )
        assert len(exp_id) == 8
        result = et.get(exp_id)
        assert result is not None
        assert result["metrics"]["sharpe"] == 1.5
