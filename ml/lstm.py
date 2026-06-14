# LSTM for time-series classification (BUY/HOLD/SELL)
# - LSTMDataset: prepares rolling windows of features/labels
# - LSTMModel: 2-layer LSTM with dropout + final linear layer


import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

LOOKBACK = 20  # Sequence length


class LSTMDataset:
    """Time-series LSTM data preparation (no lookahead bias)"""

    @staticmethod
    def prepare_sequences(
        X: np.ndarray,  # [N, num_features]
        y: np.ndarray,  # [N]
        lookback: int = LOOKBACK,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Create rolling windows: X_seq[i] = X[i-lookback:i], y[i] = y[i]

        Args:
            X: shape [N, num_features]
            y: shape [N]
            lookback: window size

        Returns:
            X_seq: shape [N-lookback, lookback, num_features]
            y_seq: shape [N-lookback]
        """
        X_seq, y_seq = [], []
        for i in range(lookback, len(X)):
            X_seq.append(X[i - lookback : i])
            y_seq.append(y[i])
        return np.array(X_seq), np.array(y_seq)


# ml/lstm.py - change LSTMModel.__init__


class LSTMModel(nn.Module):
    def __init__(
        self, input_size: int, hidden_size: int = 64, num_classes: int = 3, dropout: float = 0.2
    ):
        super().__init__()
        self.lstm1 = nn.LSTM(input_size, hidden_size, batch_first=True)  # ← Remove dropout here
        self.lstm2 = nn.LSTM(hidden_size, hidden_size, batch_first=True)  # ← Remove dropout here
        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Linear(hidden_size, num_classes)

    def forward(self, x):
        # x shape: [batch, seq_len, features]
        out, _ = self.lstm1(x)  # [batch, seq_len, hidden]
        out, _ = self.lstm2(out)  # [batch, seq_len, hidden]
        out = self.dropout(out[:, -1, :])  # Take last timestep: [batch, hidden]
        return self.fc(out)  # [batch, num_classes]


class LSTMTrainer:
    """Train LSTM with early stopping & model persistence"""

    def __init__(self, device: str = "cpu"):
        self.device = torch.device(device)

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
        """
        Train LSTM with early stopping.

        Returns:
            {"model": model, "metrics": {...}, "path": model_path}
        """
        # Prepare data
        X_train_seq, y_train_seq = LSTMDataset.prepare_sequences(X_train, y_train)
        X_val_seq, y_val_seq = LSTMDataset.prepare_sequences(X_val, y_val)

        # DataLoaders
        train_ds = TensorDataset(torch.FloatTensor(X_train_seq), torch.LongTensor(y_train_seq))
        train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)

        val_ds = TensorDataset(torch.FloatTensor(X_val_seq), torch.LongTensor(y_val_seq))
        val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)

        # Model setup
        model = LSTMModel(input_size=X_train.shape[1]).to(self.device)
        criterion = nn.CrossEntropyLoss()
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)

        # Training loop
        best_val_loss = float("inf")
        best_val_acc = 0.0
        patience_counter = 0

        for epoch in range(epochs):
            # Train
            model.train()
            train_loss = 0
            for X_batch, y_batch in train_loader:
                X_batch = X_batch.to(self.device)
                y_batch = y_batch.to(self.device)

                optimizer.zero_grad()
                logits = model(X_batch)
                loss = criterion(logits, y_batch)
                loss.backward()
                optimizer.step()

                train_loss += loss.item()

            # Validation
            model.eval()
            val_loss = 0
            val_correct = 0
            with torch.no_grad():
                for X_batch, y_batch in val_loader:
                    X_batch = X_batch.to(self.device)
                    y_batch = y_batch.to(self.device)

                    logits = model(X_batch)
                    loss = criterion(logits, y_batch)
                    val_loss += loss.item()

                    preds = torch.argmax(logits, dim=1)
                    val_correct += (preds == y_batch).sum().item()

            val_loss /= len(val_loader)
            val_acc = val_correct / len(y_val_seq)

            if (epoch + 1) % 10 == 0:
                print(
                    f"Epoch {epoch+1}/{epochs} | Train Loss: {train_loss/len(train_loader):.4f} | Val Loss: {val_loss:.4f} | Val Acc: {val_acc:.4f}"
                )

            # Early stopping
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                best_val_acc = val_acc
                patience_counter = 0
                torch.save(model.state_dict(), model_path)
            else:
                patience_counter += 1
                if patience_counter >= patience:
                    print(f"Early stopping at epoch {epoch+1}")
                    break

        # Load best model
        model.load_state_dict(torch.load(model_path))

        return {
            "model": model,
            "metrics": {"best_val_loss": float(best_val_loss), "val_acc": float(best_val_acc)},
            "path": model_path,
        }
