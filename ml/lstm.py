"""LSTM training and dataset helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

LOOKBACK = 20  # Sequence length

# Training labels arrive as {-1: SELL, 0: HOLD, 1: BUY} (see ml/labeling.py), but
# CrossEntropyLoss requires contiguous class indices {0, 1, 2}. This mapping keeps the
# class order consistent with inference, where ml/signal_fusion.py decodes
# {0: BUY, 1: HOLD, 2: SELL}.
LABEL_TO_CLASS = {1: 0, 0: 1, -1: 2}  # BUY->0, HOLD->1, SELL->2


def encode_labels(y: np.ndarray) -> np.ndarray:
    """Map signed labels {-1,0,1} to CrossEntropy class indices {0,1,2}.

    Any value outside {-1,0,1} defaults to the HOLD class (1) so the result is always a
    valid, fully-initialized class-index array — never uninitialized ``np.empty`` memory.
    """
    y = np.asarray(y)
    rounded = np.round(y).astype(np.int64)
    out = np.full(len(y), LABEL_TO_CLASS[0], dtype=np.int64)  # default -> HOLD
    for raw, cls in LABEL_TO_CLASS.items():
        out[rounded == raw] = cls
    return out


class LSTMDataset:
    @staticmethod
    def prepare_sequences(
        X: np.ndarray, y: np.ndarray, lookback: int = LOOKBACK
    ) -> tuple[np.ndarray, np.ndarray]:
        y = encode_labels(y)
        X_seq, y_seq = [], []
        for i in range(lookback, len(X)):
            X_seq.append(X[i - lookback : i])
            y_seq.append(y[i])

        if not X_seq:
            if hasattr(X, "shape") and len(X.shape) == 2:
                num_features = int(X.shape[1])
            elif X and len(X) > 0 and hasattr(X[0], "__len__"):
                num_features = int(len(X[0]))
            else:
                raise ValueError("Cannot determine num_features from empty input without shape")
            return (
                np.empty((0, lookback, num_features), dtype=np.float64),
                np.empty(0, dtype=np.int64),
            )

        return np.array(X_seq), np.array(y_seq, dtype=np.int64)


class LSTMModel(nn.Module):
    def __init__(
        self, input_size: int, hidden_size: int = 64, num_classes: int = 3, dropout: float = 0.2
    ):
        super().__init__()
        self.lstm1 = nn.LSTM(input_size, hidden_size, batch_first=True)
        self.lstm2 = nn.LSTM(hidden_size, hidden_size, batch_first=True)
        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Linear(hidden_size, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.lstm1(x)
        out, _ = self.lstm2(out)
        out = self.dropout(out[:, -1, :])
        return self.fc(out)


class LSTMTrainer:
    """Train LSTM with early stopping & model persistence."""

    def __init__(self, device: str = "cpu", random_state: int = 42) -> None:
        self.device = torch.device(device)
        self.random_state = random_state

    def train_lstm(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
        epochs: int = 100,
        batch_size: int = 32,
        patience: int = 10,
        model_path: str = "models/lstm_v1.pt",
    ) -> dict:
        # Seed all RNGs so training is reproducible run-to-run.
        torch.manual_seed(self.random_state)
        np.random.seed(self.random_state)

        X_train_seq, y_train_seq = LSTMDataset.prepare_sequences(X_train, y_train)
        if len(X_train_seq) == 0:
            raise ValueError("Training set too small after LOOKBACK windowing")
        train_ds = TensorDataset(
            torch.FloatTensor(X_train_seq).to(self.device),
            torch.LongTensor(y_train_seq).to(self.device),
        )
        loader_generator = torch.Generator()
        loader_generator.manual_seed(self.random_state)
        train_loader = DataLoader(
            train_ds, batch_size=batch_size, shuffle=True, generator=loader_generator
        )

        X_val_seq, y_val_seq = LSTMDataset.prepare_sequences(X_val, y_val)
        if len(X_val_seq) == 0:
            X_val_seq, y_val_seq = X_train_seq, y_train_seq
        val_ds = TensorDataset(
            torch.FloatTensor(X_val_seq).to(self.device),
            torch.LongTensor(y_val_seq).to(self.device),
        )
        val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)

        model = LSTMModel(input_size=int(X_train.shape[1])).to(self.device)
        criterion = nn.CrossEntropyLoss()
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)

        best_val_loss = float("inf")
        best_val_acc = 0.0
        patience_counter = 0

        Path(model_path).parent.mkdir(parents=True, exist_ok=True)

        for epoch in range(epochs):
            model.train()
            train_loss = 0.0
            for X_batch, y_batch in train_loader:
                optimizer.zero_grad()
                logits = model(X_batch)
                loss = criterion(logits, y_batch)
                loss.backward()
                optimizer.step()
                train_loss += loss.item()
            train_loss /= max(len(train_loader), 1)

            model.eval()
            val_loss = 0.0
            val_correct = 0
            val_samples = 0
            with torch.no_grad():
                for X_batch, y_batch in val_loader:
                    logits = model(X_batch)
                    loss = criterion(logits, y_batch)
                    val_loss += loss.item()
                    preds = torch.argmax(logits, dim=1)
                    val_correct += (preds == y_batch).sum().item()
                    val_samples += y_batch.shape[0]
            val_loss /= max(len(val_loader), 1)
            val_acc = val_correct / max(val_samples, 1)

            if (epoch + 1) % 10 == 0:
                print(
                    f"Epoch {epoch + 1}/{epochs} | Train Loss: {train_loss:.4f} | Val Loss: {val_loss:.4f} | Val Acc: {val_acc:.4f}"
                )

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                best_val_acc = val_acc
                patience_counter = 0
                torch.save(model.state_dict(), model_path)
            else:
                patience_counter += 1
                if patience_counter >= patience:
                    print(f"Early stopping at epoch {epoch + 1}")
                    break

        state = torch.load(model_path, map_location=self.device)
        model.load_state_dict(state)

        return {
            "model": model,
            "metrics": {"best_val_loss": float(best_val_loss), "val_acc": float(best_val_acc)},
            "path": model_path,
        }
