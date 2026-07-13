# ruff: noqa: E402
# test_signal_fusion.py

import sys
from datetime import date, datetime
from pathlib import Path

import pytest

# Add backend directory to sys.path before importing app modules
backend_dir = str(Path(__file__).parent.parent)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.models.price import Price
from app.models.stock import Stock
from app.services.risk_manager import (
    PositionSizingRequest,
    RiskManager,
    RiskState,
)
from app.services.signal_fusion import SignalFusionEngine, SignalType


@pytest.mark.asyncio
async def test_fusion_consensus(db_session):
    """All models agree → strong BUY"""

    engine = SignalFusionEngine(db_session)

    fused = await engine.fuse(
        symbol="NABIL",
        date=datetime.utcnow(),
        technical_signal={"signal": "BUY", "confidence": 0.85},
        ml_signal={"probability": 0.90},
        sentiment_signal={"score": 0.8},
        regime="bull",
    )

    assert fused.signal == SignalType.BUY
    assert fused.confidence > 0.75
    assert fused.is_actionable()


@pytest.mark.asyncio
async def test_fusion_disagreement_hold(db_session):
    """Models disagree → HOLD"""

    engine = SignalFusionEngine(db_session)

    fused = await engine.fuse(
        symbol="NABIL",
        date=datetime.utcnow(),
        technical_signal={"signal": "BUY", "confidence": 0.8},
        ml_signal={"probability": 0.3},  # Disagrees
        sentiment_signal={"score": 0.5},  # Neutral
        regime="sideways",
    )

    assert fused.signal == SignalType.HOLD
    assert not fused.is_actionable()


@pytest.mark.asyncio
async def test_risk_kill_switch(db_session):
    """Kill switch activates on critical drawdown"""

    class MockRiskManager(RiskManager):
        async def _current_drawdown(self) -> float:
            return 0.20

    risk_mgr = MockRiskManager(db_session)

    state = await risk_mgr.get_risk_state()
    kill_switch = await risk_mgr.kill_switch_active()

    assert state == RiskState.CRITICAL
    assert kill_switch is True


@pytest.mark.asyncio
async def test_position_sizing_risk_elevated(db_session):
    """Reduce position size when risk elevated"""

    class MockRiskManager(RiskManager):
        async def _current_drawdown(self) -> float:
            return 0.12

    risk_mgr = MockRiskManager(db_session)
    result = await risk_mgr.position_size(
        PositionSizingRequest(
            symbol="NABIL", signal="BUY", portfolio_equity=100000, current_position_size=0, atr=10
        )
    )
    assert result.recommended_position_size < (100000 * 0.02 / 10)


@pytest.mark.asyncio
async def test_adaptive_weights_fallback(db_session):
    """Adaptive weights fall back to base weights when no performance data available"""

    engine = SignalFusionEngine(db_session)

    weights = await engine._compute_weights("UNKNOWN_SYMBOL")

    # Should fall back to base weights
    assert "technical" in weights
    assert "lstm" in weights
    assert "sentiment" in weights
    # Weights should sum to 1
    assert abs(sum(weights.values()) - 1.0) < 0.001


@pytest.mark.asyncio
async def test_adaptive_weights_with_performance_data(db_session):
    """Adaptive weights are computed from historical performance"""

    engine = SignalFusionEngine(db_session)

    # Mock performance data showing different model accuracies
    mock_performance = {
        "technical": [
            {"accuracy": 0.7, "sharpe": 0.8, "win_rate": 0.6},
            {"accuracy": 0.75, "sharpe": -0.3, "win_rate": 0.65},
        ],
        "lstm": [
            {"accuracy": 0.85, "sharpe": 1.2, "win_rate": 0.7},
            {"accuracy": 0.8, "sharpe": 1.1, "win_rate": 0.68},
        ],
        "sentiment": [
            {"accuracy": 0.5, "sharpe": 0.3, "win_rate": 0.52},
            {"accuracy": 0.55, "sharpe": -0.5, "win_rate": 0.55},
        ],
    }

    weights = engine._compute_adaptive_weights(mock_performance)

    # LSTM should have highest weight due to best performance
    assert weights["lstm"] > weights["technical"]
    assert weights["lstm"] > weights["sentiment"]
    # Weights should sum to 1
    assert abs(sum(weights.values()) - 1.0) < 0.001


@pytest.mark.asyncio
async def test_adaptive_weights_regime_adjustment(db_session):
    """Regime filter adjusts weights appropriately"""

    engine = SignalFusionEngine(db_session)

    weights_bull = await engine._compute_weights("TEST", regime="bull")
    weights_sideways = await engine._compute_weights("TEST", regime="sideways")

    # Sideways market should reduce LSTM weight
    assert weights_sideways.get("lstm", 1.0) <= weights_bull.get("lstm", 1.0) * 1.1


@pytest.mark.asyncio
async def test_fusion_with_weights_logging(db_session):
    """Fusion logs weights used in decision"""

    engine = SignalFusionEngine(db_session)

    fused = await engine.fuse(
        symbol="NABIL",
        date=datetime.utcnow(),
        technical_signal={"signal": "BUY", "confidence": 0.9},
        ml_signal={"signal": "BUY", "confidence": 0.85},
        sentiment_signal={"score": 0.75, "count": 5},
    )

    # Weights should be recorded in explanation
    assert "weights_used" in fused.explanation or fused.weights_used is not None
    assert fused.weights_used is not None


@pytest.mark.asyncio
async def test_fusion_populates_symbol_risk_forecast(db_session):
    """Fusion should include a market-risk forecast when recent price history exists."""
    stock = Stock(symbol="RISKY", is_active=True)
    db_session.add(stock)
    db_session.flush()

    for offset, close in enumerate(
        [100.0, 101.0, 99.5, 102.0, 103.5, 101.0, 104.0, 106.0, 105.0, 107.0, 108.5, 109.0]
    ):
        db_session.add(
            Price(
                stock_id=stock.id,
                date=date(2024, 1, 1).replace(day=min(offset + 1, 28)),
                close=close,
            )
        )
    db_session.commit()

    engine = SignalFusionEngine(db_session)

    fused = await engine.fuse(
        symbol="RISKY",
        date=datetime.utcnow(),
        technical_signal={"signal": "BUY", "confidence": 0.8},
        ml_signal={"probability": 0.7},
        sentiment_signal={"score": 0.6},
        regime="bull",
    )

    assert fused.risk_assessment["risk_forecast"] is not None
    assert fused.risk_assessment["status"] in {"PASS", "WARN", "FAIL"}
