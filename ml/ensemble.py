"""Ensemble methods combining multiple model types.

Phase 14 - Experimental AI. Includes stacking, blending, and weighted
combination of Phase 7 supervised, Phase 8 LSTM, and experimental RL models.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

_workspace_root = Path(__file__).parent.parent
_backend_dir = _workspace_root / "backend"
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))

logger = logging.getLogger(__name__)


@dataclass
class EnsembleConfig:
    method: str = "weighted"
    weights: list[float] | None = None
    meta_model: str | None = None
    seed: int = 42


@dataclass
class EnsembleModel:
    name: str
    weights: np.ndarray
    predictions: np.ndarray
    metrics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "weights": self.weights.tolist(),
            "metrics": self.metrics,
        }


class EnsembleBuilder:
    def __init__(self, config: EnsembleConfig | None = None) -> None:
        self._cfg = config or EnsembleConfig()
        self._models: list[Any] = []

    def add_model(self, model: Any, weight: float | None = None) -> None:
        self._models.append((model, weight))

    def fit(self, X: np.ndarray, y: np.ndarray) -> EnsembleModel:
        preds = []
        for model, _weight in self._models:
            if hasattr(model, "predict_proba"):
                p = model.predict_proba(X)
            elif hasattr(model, "predict"):
                p = model.predict(X)
            else:
                raise TypeError(f"Unsupported model type {type(model)}")
            preds.append(np.asarray(p, dtype=np.float64))
        weights = self._compute_weights(preds, y)
        combined = self._combine(preds, weights)
        metrics = self._metrics(y, combined)
        return EnsembleModel(
            name="ensemble",
            weights=weights,
            predictions=combined,
            metrics=metrics,
        )

    def predict(self, X: np.ndarray) -> np.ndarray:
        preds = []
        for model, _ in self._models:
            if hasattr(model, "predict_proba"):
                p = model.predict_proba(X)
            elif hasattr(model, "predict"):
                p = model.predict(X)
            else:
                p = model.predict(X)
            preds.append(np.asarray(p, dtype=np.float64))
        weights = self._cfg.weights or np.ones(len(preds)) / len(preds)
        return self._combine(preds, np.asarray(weights, dtype=np.float64))

    def _compute_weights(self, preds: list[np.ndarray], y: np.ndarray) -> np.ndarray:
        if self._cfg.weights is not None:
            return np.asarray(self._cfg.weights, dtype=np.float64)
        accs = []
        for p in preds:
            labels = np.argmax(p, axis=1) if p.ndim > 1 else (p > 0.5).astype(int)
            accs.append(float(np.mean(labels == y)))
        total = sum(accs) or 1.0
        return np.asarray(accs, dtype=np.float64) / total

    def _combine(self, preds: list[np.ndarray], weights: np.ndarray) -> np.ndarray:
        out = np.zeros_like(preds[0])
        for p, w in zip(preds, weights, strict=False):
            out = out + w * p
        return out

    def _metrics(self, y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, Any]:
        labels = np.argmax(y_pred, axis=1) if y_pred.ndim > 1 else (y_pred > 0.5).astype(int)
        acc = float(np.mean(labels == y_true))
        return {"accuracy": acc, "n_models": len(self._models)}
