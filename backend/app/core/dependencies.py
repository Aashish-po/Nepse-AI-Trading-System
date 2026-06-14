from typing import Any

import pandas as pd
from app.services.signal_fusion import FusedSignal


class SignalFusionEngine:
    """Fuse multiple signal providers (technical, ML, sentiment)"""

    def __init__(self):
        self.weights = {"technical": 0.4, "lstm": 0.4, "sentiment": 0.2}

    def fuse_signals(self, signals: dict[str, dict[str, Any]]) -> dict[str, Any]:
        """
        Fuse signals from multiple providers.

        Args:
            signals: {
                "technical": {"signal": "BUY", "confidence": 0.85},
                "lstm": {"signal": "BUY", "confidence": 0.70},
                "sentiment": {"signal": "HOLD", "confidence": 0.60}
            }

        Returns:
            {"signal": "BUY", "confidence": 0.75, "explanation": {...}}
        """
        # Map signals to numeric (-1=SELL, 0=HOLD, 1=BUY)
        signal_map = {"SELL": -1, "HOLD": 0, "BUY": 1}

        weighted_score = 0.0
        total_weight = 0.0
        explanations = []

        for provider, signal_data in signals.items():
            if provider not in self.weights:
                continue

            weight = self.weights[provider]
            signal_value = signal_map.get(signal_data["signal"], 0)
            confidence = signal_data.get("confidence", 0.5)

            weighted_score += signal_value * weight * confidence
            total_weight += weight

            explanations.append(
                {
                    "provider": provider,
                    "signal": signal_data["signal"],
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
        elif normalized_score < -0.2:
            final_signal = "SELL"
        else:
            final_signal = "HOLD"

        return {
            "signal": final_signal,
            "confidence": abs(normalized_score),
            "explanation": explanations,
        }

    def fuse(
        self,
        symbol: str,
        date: pd.Timestamp,
        technical_signal: dict | None = None,
        ml_signal: dict | None = None,
        sentiment_signal: dict | None = None,
        regime: str = "bull",
        risk_state: str = "NORMAL",
    ) -> FusedSignal:
        """
        Main fusion method.

        Args:
            technical_signal: {"signal": "BUY", "confidence": 0.85, ...}
            ml_signal: {"signal": "SELL", "confidence": 0.70, ...}
            sentiment_signal: {"signal": "HOLD", "confidence": 0.60, ...}
            regime: Market regime (bull, bear, sideways)
            risk_state: Current system risk state
        """

        signals = {"technical": technical_signal, "ml": ml_signal, "sentiment": sentiment_signal}
        signals = {k: v for k, v in signals.items() if v}

        fusion_result = self.fuse_signals(signals)

        return FusedSignal(
            symbol=symbol,
            date=date,
            signal=fusion_result["signal"],
            confidence=fusion_result["confidence"],
            explanation=fusion_result["explanation"],
            risk_assessment={"regime": regime, "risk_state": risk_state},
            raw_scores={k: v.get("confidence", 0.5) for k, v in signals.items() if v},
            weights_used=self.weights,
        )


class get_current_User:
    """Fuse multiple signal providers (technical, ML, sentiment)"""

    def __init__(self):
        self.weights = {"technical": 0.4, "lstm": 0.4, "sentiment": 0.2}

    """Mock function to get current user from auth token."""

    async def __call__(self):
        # In real implementation, decode JWT and fetch user from DB
        return {"id": 1, "username": "testuser", "role": "trader"}

    def get_db(self):
        """Mock function to get DB session."""

        # In real implementation, return actual DB session
        class MockDBSession:
            async def query(self, query: str, params: list | None = None):
                return None  # Replace with actual query logic

        return MockDBSession()


def get_current_user(self):
    """Mock function to get current user from auth token."""
    # In real implementation, decode JWT and fetch user from DB
    return {"id": 1, "username": "testuser", "role": "trader"}
