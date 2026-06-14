import numpy as np
import torch


class LSTMSignalProvider:
    """Generate BUY/SELL/HOLD from LSTM predictions"""

    def __init__(self, model_path: str):
        self.model = torch.load(model_path)

    def generate_signal(self, features: np.ndarray) -> dict:
        """
        features: [lookback=20, num_features]

        Returns: {"signal": "BUY"|"SELL"|"HOLD", "confidence": 0.0-1.0}
        """
        X = torch.FloatTensor(features).unsqueeze(0)  # [1, 20, features]

        with torch.no_grad():
            logits = self.model(X)  # [1, 3]
            probs = torch.softmax(logits, dim=1)[0]  # [3]
            pred_class = torch.argmax(probs)
            confidence = float(probs[pred_class])

        signal_map = {0: "BUY", 1: "HOLD", 2: "SELL"}
        return {"signal": signal_map[int(pred_class)], "confidence": confidence, "provider": "lstm"}
