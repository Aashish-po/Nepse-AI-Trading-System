# test_signal_fusion.py

from datetime import datetime

import pytest

from backend.app.services.risk_manager import (
    PositionSizingRequest,
    RiskManager,
    RiskState,
)
from backend.app.services.signal_fusion import SignalFusionEngine, SignalType


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
