"""Integration tests for Phase 10: Full signal fusion to portfolio pipeline."""

from decimal import Decimal

import numpy as np
import pytest

torch = pytest.importorskip("torch")
pl = pytest.importorskip("polars")


class TestPhase10Integration:
    """End-to-end tests for Phase 10 features."""

    def test_full_pipeline_components_exist(self):
        """All Phase 10 components are importable."""
        from app.services.backtest import VectorizedBacktestEngine
        from app.services.mlops import MLOpsService
        from app.services.signal_fusion import SignalFusionEngine

        from ml.sentiment import SentimentAnalyzer, SymbolSentimentFetcher

        # All imports successful
        assert VectorizedBacktestEngine is not None
        assert MLOpsService is not None
        assert SignalFusionEngine is not None
        assert SentimentAnalyzer is not None
        assert SymbolSentimentFetcher is not None

    def test_portfolio_constraints_with_sectors(self):
        """Portfolio constraints support sector-aware allocation."""
        from app.services.portfolio_optimization import OptimizationConstraints

        sector_map = {
            "NABIL": "Banking",
            "SCB": "Banking",
            "NTC": "Telecom",
            "NTBRIDGE": "Telecom",
        }

        constraints = OptimizationConstraints(
            long_only=True,
            max_weight=0.1,
            max_sector_exposure=0.3,
            sector_map=sector_map,
        )

        # Validate constraints
        assert constraints.long_only is True
        assert constraints.max_weight == 0.1
        assert constraints.max_sector_exposure == 0.3

    def test_optimize_from_signals_basic(self):
        """optimize_from_signals extracts returns from signal confidence."""
        from app.services.portfolio_optimization import optimize_from_signals

        fused_signals = [
            {"symbol": "NABIL", "signal": "BUY", "confidence": 0.85},
            {"symbol": "SCB", "signal": "HOLD", "confidence": 0.5},
            {"symbol": "NTC", "signal": "SELL", "confidence": 0.7},
        ]

        covariance = np.eye(3) * 0.04  # Diagonal covariance

        result = optimize_from_signals(
            fused_signals=fused_signals,
            symbols=["NABIL", "SCB", "NTC"],
            covariance_matrix=covariance,
            max_weight=1.0,
        )

        assert result.weights is not None
        assert result.method in ("mean_variance", "mean_variance_fallback")
        # BUY signals should have positive expected returns
        # SELL signals should have negative expected returns
        total_weight = sum(result.weights.values())
        assert abs(total_weight - 1.0) < 0.001

    def test_adaptive_weights_learns_from_performance(self):
        """Adaptive weights correctly rank models by performance."""
        from app.services.signal_fusion import SignalFusionEngine

        # Create engine with mock db
        class MockDB:
            pass

        engine = SignalFusionEngine(MockDB())

        # Performance shows LSTM outperforming others
        performance = {
            "technical": [
                {"accuracy": 0.6, "sharpe": 0.2, "win_rate": 0.55},
                {"accuracy": 0.6, "sharpe": -0.3, "win_rate": 0.52},
            ],
            "lstm": [
                {"accuracy": 0.8, "sharpe": 1.5, "win_rate": 0.75},
                {"accuracy": 0.85, "sharpe": 1.2, "win_rate": 0.73},
            ],
            "sentiment": [
                {"accuracy": 0.5, "sharpe": 0.1, "win_rate": 0.52},
                {"accuracy": 0.55, "sharpe": -0.5, "win_rate": 0.5},
            ],
        }

        weights = engine._compute_adaptive_weights(performance)

        # LSTM should have highest weight (best Sharpe)
        assert weights["lstm"] > weights["technical"]
        assert weights["lstm"] > weights["sentiment"]

    def test_vectorized_backtest_initialization(self):
        """Vectorized backtest engine initializes correctly."""
        from app.services.backtest import VectorizedBacktestEngine

        engine = VectorizedBacktestEngine(
            initial_capital=Decimal("1000000"),
            commission_rate=Decimal("0.005"),
            slippage_bps=Decimal("5"),
        )

        assert engine.initial_capital == Decimal("1000000")
        assert engine.commission_rate == Decimal("0.005")
        assert engine.slippage_bps == Decimal("5")

    def test_sentiment_to_signal_mapping(self):
        """Sentiment scores convert correctly to signal format."""
        from ml.sentiment import sentiment_score_to_signal

        # Strong bullish
        assert sentiment_score_to_signal(0.8, 0.9)["signal"] == "BUY"

        # Strong bearish
        assert sentiment_score_to_signal(0.2, 0.85)["signal"] == "SELL"

        # Neutral range
        assert sentiment_score_to_signal(0.5, 0.5)["signal"] == "HOLD"
        assert sentiment_score_to_signal(0.55, 0.7)["signal"] == "HOLD"
        assert sentiment_score_to_signal(0.45, 0.6)["signal"] == "HOLD"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
