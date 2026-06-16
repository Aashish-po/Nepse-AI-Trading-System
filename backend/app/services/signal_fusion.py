# Signal Fusion Engine
# Combines the best of both implementations: backend/service version + LSTM provider from ml version

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

import numpy as np
import torch

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


class LSTMSignalProvider:
    """Generate BUY/SELL/HOLD signals from LSTM predictions"""

    def __init__(self, model_path: str, device: str = "cpu"):
        self.device = torch.device(device)
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"LSTM model not found at {model_path}")
        self.model = torch.load(model_path, map_location=self.device)
        self.model.eval()
        logger.info(f"Loaded LSTM model from {model_path}")

    def generate_signal(self, features: np.ndarray) -> dict[str, Any]:
        """
        Generate signal from LSTM prediction.

        Args:
            features: [lookback=20, num_features]

        Returns:
            {"signal": "BUY"|"SELL"|"HOLD", "confidence": 0.0-1.0, "provider": "lstm"}
        """
        X = torch.FloatTensor(features).unsqueeze(0).to(self.device)  # [1, 20, features]

        with torch.no_grad():
            logits = self.model(X)  # [1, 3]
            probs = torch.softmax(logits, dim=1)[0]  # [3]
            pred_class = torch.argmax(probs)
            confidence = float(probs[pred_class])

        signal_map = {0: "BUY", 1: "HOLD", 2: "SELL"}

        return {"signal": signal_map[int(pred_class)], "confidence": confidence, "provider": "lstm"}


class SignalFusionEngine:
    """
    Fuse technical, ML (LSTM), sentiment, and regime signals into a single advisory output.
    """

    def __init__(self, db_session):
        self.db = db_session
        self.min_models_active = 2  # Require at least 2 models
        self.confidence_threshold = 0.65
        # Default weights - can be overridden by dynamic computation
        self.base_weights = {"technical": 0.3, "lstm": 0.4, "sentiment": 0.3}

    async def fuse(
        self,
        symbol: str,
        date: datetime,
        technical_signal: dict[str, Any] | None = None,
        ml_signal: dict[str, Any] | None = None,
        sentiment_signal: dict[str, Any] | None = None,
        regime: str | None = None,
        risk_state: str | None = None,
    ) -> FusedSignal:
        """
        Main fusion logic.

        Inputs:
        - technical_signal: {"signal": "BUY"/"SELL", "confidence": 0.8, "features": [...]}
        - ml_signal: {"signal": "BUY"/"SELL"/"HOLD", "confidence": 0.75}  # Can be from LSTM or other ML
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
            # ML signal can be in different formats - handle both
            if "probability" in ml_signal:
                # Old format from XGBoost etc.
                raw_scores["lstm"] = ml_signal.get("probability", 0.5)
            elif "signal" in ml_signal and "confidence" in ml_signal:
                # New format from LSTMSignalProvider
                signal_val = self._score_signal(ml_signal)
                raw_scores["lstm"] = signal_val
            else:
                # Fallback
                raw_scores["lstm"] = ml_signal.get("score", 0.5)

        if sentiment_signal:
            raw_scores["sentiment"] = sentiment_signal.get("score", 0.5)

        # 3. Compute dynamic weights (recent model performance)
        weights = await self._compute_weights(symbol, regime)

        # 4. Apply regime filter
        if regime == "sideways":
            weights["lstm"] *= 0.7  # Reduce ML confidence in range-bound markets

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

    def fuse_signals(self, signals: dict[str, dict]) -> dict[str, Any]:
        """
        Backward-compatible method for the ml/signal_fusion interface.

        Args:
            signals: {
                "technical": {"signal": "BUY", "confidence": 0.85},
                "lstm": {"signal": "BUY", "confidence": 0.70},
                "sentiment": {"signal": "HOLD", "confidence": 0.60}
            }

        Returns:
            {"signal": "BUY", "confidence": 0.75, "explanation": {...}}
        """
        # Convert the old format to the new format
        technical_signal = signals.get("technical")
        ml_signal = signals.get("lstm")
        sentiment_signal = signals.get("sentiment")

        # For compatibility, we'll create a mock signal with score
        if sentiment_signal and "signal" in sentiment_signal:
            # Convert signal to score for backward compatibility
            signal_map = {"BUY": 0.8, "SELL": 0.2, "HOLD": 0.5}
            score = signal_map.get(sentiment_signal["signal"].upper(), 0.5)
            sentiment_signal = {"score": score, "count": 1}  # Mock count

        # Import datetime for the date parameter
        # Use the main fuse method (we'll run it synchronously for compatibility)
        import asyncio
        from datetime import datetime

        try:
            # Try to get the running loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Already inside a running loop; this sync shim cannot await the real
                # async fuse(), so fall back to the simplified synchronous fusion.
                return self._legacy_fuse_signals(signals)
            else:
                fused = loop.run_until_complete(
                    self.fuse(
                        symbol="TEST",
                        date=datetime.now(),
                        technical_signal=technical_signal,
                        ml_signal=ml_signal,
                        sentiment_signal=sentiment_signal,
                    )
                )
        except RuntimeError:
            # No event loop, we'll use simplified logic for test compatibility
            return self._legacy_fuse_signals(signals)

        # Convert FusedSignal to the expected dict format
        return {
            "signal": fused.signal.value,
            "confidence": fused.confidence,
            "provider": "fusion",
            "explanation": fused.explanation,
        }

    def _legacy_fuse_signals(self, signals: dict[str, dict]) -> dict[str, Any]:
        """
        Simplified signal fusion for backward compatibility with tests.
        This mimics the logic from the original ml/signal_fusion.py
        """
        # Map signals to numeric (-1=SELL, 0=HOLD, 1=BUY)
        signal_map = {"SELL": -1, "HOLD": 0, "BUY": 1}

        weighted_score = 0.0
        total_weight = 0.0
        explanations = []

        # Use weights from the base class or defaults
        weights = {"technical": 0.3, "lstm": 0.4, "sentiment": 0.3}

        for provider, signal_data in signals.items():
            if provider not in weights:
                continue

            weight = weights[provider]
            signal_value = signal_map.get(signal_data.get("signal", "HOLD").upper(), 0)
            confidence = signal_data.get("confidence", 0.5)

            weighted_score += signal_value * weight * confidence
            total_weight += weight

            explanations.append(
                {
                    "provider": provider,
                    "signal": signal_data.get("signal", "HOLD"),
                    "confidence": confidence,
                    "weight": weight,
                }
            )

        # Convert back to signal
        if total_weight > 0:
            normalized_score = weighted_score / total_weight
        else:
            normalized_score = 0

        if normalized_score > 0.2:
            final_signal = "BUY"
            final_confidence = min(normalized_score, 1.0)
        elif normalized_score < -0.2:
            final_signal = "SELL"
            final_confidence = min(abs(normalized_score), 1.0)
        else:
            final_signal = "HOLD"
            final_confidence = 0.5

        return {
            "signal": final_signal,
            "confidence": final_confidence,
            "provider": "fusion",
            "explanation": explanations,
        }

    def _score_signal(self, signal_dict: dict[str, Any]) -> float:
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
        For now, return base weights but this can be enhanced to query performance metrics.
        """
        # Default equal weights
        base_weights = self.base_weights.copy()

        # TODO: Fetch backtest performance from DB and adjust weights accordingly
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

    # Convenience method to generate LSTM signal from features
    def generate_lstm_signal(self, symbol: str, features: np.ndarray) -> dict[str, Any] | None:
        """
        Generate an LSTM signal for a symbol given its features.
        Looks for the trained model and generates a signal if found.
        """
        model_path = f"models/lstm_{symbol}_v1.pt"
        try:
            provider = LSTMSignalProvider(model_path=model_path, device="cpu")
            return provider.generate_signal(features)
        except FileNotFoundError:
            logger.warning(f"No LSTM model found for {symbol} at {model_path}")
            return None
        except Exception as e:
            logger.error(f"Error generating LSTM signal for {symbol}: {e}")
            return None
