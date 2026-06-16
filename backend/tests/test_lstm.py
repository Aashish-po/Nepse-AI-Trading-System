import importlib
import sys
from pathlib import Path

import numpy as np
import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

torch = pytest.importorskip("torch")
ml_lstm = importlib.import_module("ml.lstm")
LSTMDataset = ml_lstm.LSTMDataset
LSTMModel = ml_lstm.LSTMModel


def test_lstm_data_prep():
    """LSTM sequence preparation is lookahead-free and encodes signed labels."""
    X = np.random.randn(100, 10)  # [100 timesteps, 10 features]
    # Training labels are signed {-1: SELL, 0: HOLD, 1: BUY}; prepare_sequences remaps
    # them to CrossEntropy class indices {0,1,2} consistent with inference.
    y = np.array([-1, 0, 1] * 33 + [-1])  # [100 signed labels]

    X_seq, y_seq = LSTMDataset.prepare_sequences(X, y, lookback=20)

    assert X_seq.shape == (80, 20, 10), f"Expected (80, 20, 10), got {X_seq.shape}"
    assert y_seq.shape == (80,), f"Expected (80,), got {y_seq.shape}"
    # y_seq[i] corresponds to X[i-20:i]; labels are the encoded versions of y[20:].
    assert np.array_equal(y_seq, ml_lstm.encode_labels(y)[20:])


def test_lstm_forward():
    """LSTM forward pass produces 3-class logits"""
    model = LSTMModel(input_size=10, hidden_size=32, num_classes=3)
    X = np.random.randn(8, 20, 10)  # [batch=8, seq=20, features=10]
    X_tensor = torch.FloatTensor(X)

    logits = model(X_tensor)
    assert logits.shape == (8, 3), f"Expected (8, 3), got {logits.shape}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
