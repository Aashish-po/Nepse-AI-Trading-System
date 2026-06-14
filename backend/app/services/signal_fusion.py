# Signal Fusion Engine

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class SignalType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class FusedSignal:
    symbol: str
    date: datetime
    signal: SignalType
    confidence: float  # 0.0-1.0
    explanation: dict[str, Any]
    risk_assessment: dict[str, Any]
    raw_scores: dict[str, float]  # individual model scores
    weights_used: dict[str, float]  # model weights in fusion

    def is_actionable(self) -> bool:
        """Only BUY/SELL with confidence >= 0.65"""
        if self.signal == SignalType.HOLD:
            return False
        return self.confidence >= 0.65


class SignalFusionEngine:
    """
    Fuse technical, ML, sentiment, and regime signals into a single advisory output.
    """

    def __init__(self, db_session):
        self.db = db_session
        self.min_models_active = 2  # Require at least 2 models
        self.confidence_threshold = 0.65

    async def fuse(
        self,
        symbol: str,
        date: datetime,
        technical_signal: dict | None = None,
        ml_signal: dict | None = None,
        sentiment_signal: dict | None = None,
        regime: str | None = None,
        risk_state: str | None = None,
    ) -> FusedSignal:
        """
        Main fusion logic.

        Inputs:
        - technical_signal: {"signal": "BUY"/"SELL", "confidence": 0.8, "features": [...]}
        - ml_signal: {"probability": 0.75, "model": "xgboost", "version": "1.0"}
        - sentiment_signal: {"score": 0.6, "count": 10}  # 0=very negative, 1=very positive
        - regime: "bull" / "bear" / "sideways"
        - risk_state: "normal" / "elevated" / "critical"

        Returns: FusedSignal with weighted consensus and explanation
        """

        # 1. Validate inputs
        available_signals = sum(
            [technical_signal is not None, ml_signal is not None, sentiment_signal is not None]
        )

        if available_signals < self.min_models_active:
            logger.warning(
                f"Insufficient signal sources for {symbol}: only {available_signals} available"
            )
            return FusedSignal(
                symbol=symbol,
                date=date,
                signal=SignalType.HOLD,
                confidence=0.0,
                explanation={"reason": "Insufficient signal sources"},
                risk_assessment={"status": "hold_only"},
                raw_scores={},
                weights_used={},
            )

        # 2. Compute raw scores (normalized 0-1, 0.5 = neutral)
        raw_scores = {}

        if technical_signal:
            raw_scores["technical"] = self._score_signal(technical_signal)

        if ml_signal:
            raw_scores["ml"] = ml_signal.get("probability", 0.5)

        if sentiment_signal:
            raw_scores["sentiment"] = sentiment_signal.get("score", 0.5)

        # 3. Compute dynamic weights (recent model performance)
        weights = await self._compute_weights(symbol, regime)

        # 4. Apply regime filter
        if regime == "sideways":
            weights["ml"] *= 0.7  # Reduce ML confidence in range-bound markets

        # 5. Fuse into consensus
        fused_score = sum(
            raw_scores[model] * weights.get(model, 0.0) for model in raw_scores.keys()
        ) / sum(weights.get(model, 0.0) for model in raw_scores.keys())

        # 6. Map score to signal
        signal, confidence = self._score_to_signal(fused_score)

        # 7. Apply risk checks
        risk_assessment = await self._assess_risk(symbol, signal, risk_state)

        if risk_assessment["action"] == "HOLD_ONLY":
            signal = SignalType.HOLD
            confidence *= 0.5

        # 8. Build explanation
        explanation = {
            "raw_scores": raw_scores,
            "fused_score": fused_score,
            "regime": regime,
            "risk_state": risk_state,
            "models_used": list(raw_scores.keys()),
            "dominant_signal": max(raw_scores.items(), key=lambda x: abs(x[1] - 0.5))[0],
        }

        return FusedSignal(
            symbol=symbol,
            date=date,
            signal=signal,
            confidence=min(confidence, 1.0),
            explanation=explanation,
            risk_assessment=risk_assessment,
            raw_scores=raw_scores,
            weights_used=weights,
        )

    def _score_signal(self, signal_dict: dict) -> float:
        """Convert BUY/SELL to 0-1 score."""
        sig = signal_dict.get("signal", "HOLD")
        conf = signal_dict.get("confidence", 0.5)

        if sig == "BUY":
            return 0.5 + (conf * 0.5)  # 0.5-1.0
        elif sig == "SELL":
            return 0.5 - (conf * 0.5)  # 0.0-0.5
        else:  # HOLD
            return 0.5

    async def _compute_weights(self, symbol: str, regime: str | None = None) -> dict[str, float]:
        """
        Compute dynamic weights based on recent model performance.

        Fetch last 30 days of backtest results and Sharpe ratios.
        """
        # Default equal weights
        base_weights = {"technical": 0.3, "ml": 0.4, "sentiment": 0.3}

        # TODO: Fetch backtest performance from DB
        # For now, return base weights

        return base_weights

    def _score_to_signal(self, fused_score: float) -> tuple[SignalType, float]:
        """
        Map fused score (0-1) to signal + confidence.

        0.0-0.35: SELL (confidence = 1 - score/0.35)
        0.35-0.65: HOLD (confidence = 1 - abs(score - 0.5)/0.15)
        0.65-1.0: BUY (confidence = (score - 0.5) / 0.5)
        """
        if fused_score < 0.35:
            return SignalType.SELL, min(1.0, (0.35 - fused_score) / 0.35)
        elif fused_score > 0.65:
            return SignalType.BUY, min(1.0, (fused_score - 0.5) / 0.5)
        else:
            return SignalType.HOLD, 1.0 - abs(fused_score - 0.5) / 0.15

    async def _assess_risk(
        self, symbol: str, signal: SignalType, risk_state: str | None = None
    ) -> dict[str, Any]:
        """
        Check risk guardrails before allowing signal.
        """

        risk_checks = {
            "portfolio_drawdown": await self._check_drawdown(),
            "position_size": await self._check_position_size(symbol),
            "sector_exposure": await self._check_sector_exposure(symbol),
            "daily_loss_limit": await self._check_daily_loss(),
        }

        failures = [check for check, passed in risk_checks.items() if not passed]

        return {
            "status": "PASS" if not failures else "FAIL",
            "action": "PROCEED" if not failures else "HOLD_ONLY",
            "failed_checks": failures,
            "risk_state": risk_state or "normal",
        }

    async def _check_drawdown(self) -> bool:
        """Portfolio drawdown < 15%?"""
        # TODO: Query portfolio snapshots
        return True

    async def _check_position_size(self, symbol: str) -> bool:
        """Position size < 10% of portfolio?"""
        # TODO: Query holdings
        return True

    async def _check_sector_exposure(self, symbol: str) -> bool:
        """Sector exposure < 30%?"""
        # TODO: Query sector holdings
        return True

    async def _check_daily_loss(self) -> bool:
        """Daily loss < 2%?"""
        # TODO: Query daily P&L
        return True
