import numpy as np


class LSTMSignalProvider:
    """Generate BUY/SELL/HOLD signals from LSTM predictions"""

    def __init__(self, model_path: str, device: str = "cpu"):
        import torch

        self.device = torch.device(device)
        self.model = torch.load(model_path, map_location=self.device)
        self.model.eval()

    def generate_signal(self, features: np.ndarray) -> dict:
        """
        Generate signal from LSTM prediction.

        Args:
            features: [lookback=20, num_features]

        Returns:
            {"signal": "BUY"|"SELL"|"HOLD", "confidence": 0.0-1.0, "provider": "lstm"}
        """
        import torch

        X = torch.FloatTensor(features).unsqueeze(0).to(self.device)  # [1, 20, features]

        with torch.no_grad():
            logits = self.model(X)  # [1, 3]
            probs = torch.softmax(logits, dim=1)[0]  # [3]
            pred_class = torch.argmax(probs)
            confidence = float(probs[pred_class])

        signal_map = {0: "BUY", 1: "HOLD", 2: "SELL"}

        return {"signal": signal_map[int(pred_class)], "confidence": confidence, "provider": "lstm"}


class SignalFusionEngine:
    """Fuse multiple signal providers (technical, ML, sentiment)"""

    def __init__(self):
        self.weights = {"technical": 0.4, "lstm": 0.4, "sentiment": 0.2}

    def fuse_signals(self, signals: dict[str, dict]) -> dict:
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


if __name__ == "__main__":
    pass
