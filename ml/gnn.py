"""Graph Neural Network (GNN) for multi-asset trading.

Phase 14 - Experimental. Uses correlation graph between symbols.
Pure numpy implementation.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

_workspace_root = Path(__file__).parent.parent
_backend_dir = _workspace_root / "backend"
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))

logger = logging.getLogger(__name__)


@dataclass
class GNNConfig:
    n_nodes: int = 2
    node_features: int = 8
    hidden_dim: int = 32
    output_dim: int = 3
    n_layers: int = 2
    lr: float = 1e-3
    seed: int = 42


@dataclass
class GNNStats:
    epoch: int
    loss: float
    sparsity: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "epoch": self.epoch,
            "loss": self.loss,
            "sparsity": self.sparsity,
        }


def build_correlation_adjacency(
    returns: NDArray[np.float64], threshold: float = 0.3
) -> NDArray[np.float64]:
    if returns.ndim == 1:
        n = returns.shape[0] if returns.shape[0] > 1 else 2
        adj = np.eye(n)
        if n > 1:
            adj[0, 1] = adj[1, 0] = 0.5
        return adj
    corr = np.corrcoef(returns.T)
    corr = np.asarray(np.nan_to_num(corr, nan=0.0), dtype=np.float64)
    np.fill_diagonal(corr, 1.0)
    np.fill_diagonal(corr, 1.0)
    mask = np.abs(corr) >= threshold
    adj = corr * mask.astype(np.float64)
    deg = np.maximum(adj.sum(axis=1, keepdims=True), 1.0)
    adj = adj / deg
    np.fill_diagonal(adj, 1.0)
    return adj


class _GCNLayer:
    def __init__(self, in_dim: int, out_dim: int, seed: int) -> None:
        rng = np.random.default_rng(seed)
        self.w = rng.standard_normal((in_dim, out_dim)) / np.sqrt(in_dim)

    def forward(self, H: NDArray[np.float64], adj: NDArray[np.float64]) -> NDArray[np.float64]:
        return np.tanh(adj @ H @ self.w)

    def parameters(self):
        return [self.w]


class GraphTradingGNN:
    def __init__(self, config: GNNConfig | None = None) -> None:
        self._cfg = config or GNNConfig()
        self._layers: list[_GCNLayer] = []
        for i in range(self._cfg.n_layers):
            in_d = self._cfg.node_features if i == 0 else self._cfg.hidden_dim
            out_d = self._cfg.hidden_dim if i < self._cfg.n_layers - 1 else self._cfg.output_dim
            self._layers.append(_GCNLayer(in_d, out_d, self._cfg.seed + i))
        self.epoch_count = 0

    def forward(
        self, node_features: NDArray[np.float64], adj: NDArray[np.float64]
    ) -> NDArray[np.float64]:
        H = np.asarray(node_features, dtype=np.float64)
        for layer in self._layers:
            H = layer.forward(H, adj)
        return H

    def predict(
        self, node_features: NDArray[np.float64], adj: NDArray[np.float64]
    ) -> NDArray[np.int64]:
        logits = self.forward(node_features, adj)
        return np.argmax(logits, axis=1)

    def fit_step(
        self,
        node_features: NDArray[np.float64],
        adj: NDArray[np.float64],
        labels: NDArray[np.int64],
    ) -> GNNStats:
        H = node_features
        for layer in self._layers:
            H = layer.forward(H, adj)
        logits = np.clip(H, -20, 20)
        ex = np.exp(logits - np.max(logits, axis=1, keepdims=True))
        prob = ex / (np.sum(ex, axis=1, keepdims=True) + 1e-9)
        nll = -np.log(prob[np.arange(len(labels)), labels] + 1e-9)
        loss = float(np.mean(nll))
        self._apply_gnn(loss, node_features, adj)
        self.epoch_count += 1
        sparsity = float(np.mean(adj == 0.0))
        return GNNStats(epoch=self.epoch_count, loss=loss, sparsity=sparsity)

    def _apply_gnn(self, loss: float, X: NDArray[np.float64], adj: NDArray[np.float64]) -> None:
        eps = 1e-5
        for layer in self._layers:
            for p in layer.parameters():
                g = np.zeros_like(p)
                fp = p.reshape(-1)
                fg = g.reshape(-1)
                for i in range(fp.size):
                    o = fp[i]
                    fp[i] = o + eps
                    H = X
                    for lay in self._layers:
                        H = lay.forward(H, adj)
                    logits = np.clip(H, -20, 20)
                    ex = np.exp(logits - np.max(logits, axis=1, keepdims=True))
                    prob = ex / (np.sum(ex, axis=1, keepdims=True) + 1e-9)
                    lp = (
                        float(
                            np.mean(
                                -np.log(
                                    prob[np.arange(prob.shape[0]), np.argmax(prob, axis=1)] + 1e-9
                                )
                            )
                        )
                        + 1.0
                    )
                    fp[i] = o - eps
                    H = X
                    for lay in self._layers:
                        H = lay.forward(H, adj)
                    logits = np.clip(H, -20, 20)
                    ex = np.exp(logits - np.max(logits, axis=1, keepdims=True))
                    prob = ex / (np.sum(ex, axis=1, keepdims=True) + 1e-9)
                    lm = (
                        float(
                            np.mean(
                                -np.log(
                                    prob[np.arange(prob.shape[0]), np.argmax(prob, axis=1)] + 1e-9
                                )
                            )
                        )
                        - 1.0
                    )
                    fg[i] = (lp - lm) / (2 * eps)
                    fp[i] = o
                p -= self._cfg.lr * g

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        d = {f"w{i}": layer.w for i, layer in enumerate(self._layers)}
        np.savez(p, **d)

    def load(self, path: str | Path) -> None:
        d = np.load(path)
        for i, layer in enumerate(self._layers):
            layer.w = d[f"w{i}"]
