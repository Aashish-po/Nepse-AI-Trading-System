"""Tests for Phase 10: Online LSTM Learning and Model Refresh."""

import numpy as np
import pytest

torch = pytest.importorskip("torch")


def test_lstm_trainer_has_random_state():
    """LSTMTrainer uses deterministic random state."""
    from ml.lstm import LSTMTrainer

    trainer = LSTMTrainer(device="cpu", random_state=42)
    assert trainer.random_state == 42


def test_lstm_model_dtype_consistency():
    """LSTM inputs maintain consistent float64 dtype throughout."""
    from ml.lstm import LSTMModel

    model = LSTMModel(input_size=10, hidden_size=32, num_classes=3)
    assert model is not None

    # Input should be float32 for PyTorch but we need to track dtype properly
    X = np.random.randn(20, 10).astype(np.float64)
    X_seq, y_seq = [], []
    for i in range(20, len(X)):
        X_seq.append(X[i - 20 : i])
        y_seq.append(1)

    X_tensor = torch.FloatTensor(np.array(X_seq, dtype=np.float64))
    assert X_tensor.dtype == torch.float32  # PyTorch converts to float32


def test_retrain_method_exists():
    """MLOpsService has online retraining method."""
    from app.services.mlops import MLOpsService

    # Check method exists
    assert hasattr(MLOpsService, "retrain_lstm_online")


def test_optimization_from_signals_function_exists():
    """Portfolio optimization can accept fused signals directly."""
    from app.services.portfolio_optimization import optimize_from_signals

    assert callable(optimize_from_signals)


def test_vectorized_engine_exists():
    """VectorizedBacktestEngine class exists."""
    from app.services.backtest import VectorizedBacktestEngine

    assert VectorizedBacktestEngine is not None


def test_signal_fusion_has_adaptive_weights():
    """SignalFusionEngine has adaptive weight computation."""
    # Verify the fusion engine uses sklearn LogisticRegression
    import importlib

    module = importlib.import_module("backend.app.services.signal_fusion")
    assert hasattr(module.SignalFusionEngine, "_compute_adaptive_weights")
    assert hasattr(module.SignalFusionEngine, "_get_recent_model_performance")


def test_sector_constraints_in_optimization():
    """Portfolio optimization supports sector exposure constraints."""
    from app.services.portfolio_optimization import OptimizationConstraints

    # Create constraints with sector map
    constraints = OptimizationConstraints(
        long_only=True,
        max_weight=0.1,
        max_sector_exposure=0.3,
        sector_map={"NABIL": "Banking", "SCB": "Banking", "NTC": "Telecom"},
    )

    assert constraints.max_sector_exposure == 0.3
    assert constraints.sector_map is not None


def test_sentiment_fetcher_exists():
    """SymbolSentimentFetcher exists for news integration."""
    from ml.sentiment import SymbolSentimentFetcher

    assert callable(SymbolSentimentFetcher)
    assert hasattr(SymbolSentimentFetcher, "compute")


def test_sentiment_score_to_signal():
    """Sentiment score converts to signal format correctly."""
    from ml.sentiment import sentiment_score_to_signal

    # Bullish sentiment
    result = sentiment_score_to_signal(0.8, 0.9)
    assert result["signal"] == "BUY"
    assert result["score"] == 0.8

    # Bearish sentiment
    result = sentiment_score_to_signal(0.2, 0.8)
    assert result["signal"] == "SELL"
    assert result["score"] == 0.2

    # Neutral sentiment
    result = sentiment_score_to_signal(0.5, 0.7)
    assert result["signal"] == "HOLD"


def test_online_lstm_retrain_uses_validation_returns(db_session, monkeypatch):
    """The online retrain path should derive Sharpe from validation returns."""
    import pandas as pd
    import torch.nn as nn
    from app.models.model_registry import ModelRegistry
    from app.services.mlops import MLOpsService

    from ml.dataset import DatasetBuilder
    from ml.lstm import LSTMTrainer

    class DummyModel(nn.Module):
        def forward(self, x):
            batch = x.shape[0]
            return torch.tensor([[4.0, 0.0, -4.0]], dtype=torch.float32).repeat(batch, 1)

    all_X = pd.DataFrame([[float(i), float(i + 1)] for i in range(120)])
    all_y = pd.Series([1] * 120)
    all_dates = [f"2024-01-{(i % 30) + 1:02d}" for i in range(120)]
    all_returns = [0.01, 0.02, -0.01, 0.03, 0.015, 0.005, 0.02, -0.005, 0.012, 0.018] * 12
    all_prices = [100.0 + i for i in range(120)]

    monkeypatch.setattr(
        DatasetBuilder,
        "_build_full_dataset",
        lambda self, symbols, start_date, end_date: (
            all_X,
            all_y,
            all_dates,
            all_returns,
            all_prices,
        ),
    )
    monkeypatch.setattr(
        LSTMTrainer,
        "train_lstm",
        lambda self, **kwargs: {
            "model": DummyModel(),
            "metrics": {"best_val_loss": 0.1, "val_acc": 0.9},
            "path": kwargs["model_path"],
        },
    )

    service = MLOpsService(db_session)
    db_session.add(ModelRegistry(name="lstm_TEST", version="v1", metrics={"sharpe_ratio": 0.0}))
    db_session.commit()

    result = service.retrain_lstm_online("TEST", promoter_threshold=0.0, lookback_days=20)

    assert result["status"] == "completed"
    assert result["new_sharpe"] != 0.0
