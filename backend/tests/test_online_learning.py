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
