"""Model evaluation for classification and trading metrics."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
from numpy.typing import NDArray
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    f1_score,
    log_loss,
    roc_auc_score,
)
from sqlalchemy.orm import Session

try:
    # Optional; used for Brier score for multi-class only
    from sklearn.preprocessing import label_binarize

    _HAS_LABEL_BINARIZE = True
except Exception:  # pragma: no cover
    label_binarize = None
    _HAS_LABEL_BINARIZE = False


logger = logging.getLogger(__name__)


class ModelEvaluator:
    def __init__(self, session: Session) -> None:
        self._session = session

    def evaluate_classification(
        self,
        model: Any,
        X: NDArray[np.float64],
        y_true: NDArray[np.float64],
    ) -> dict[str, float]:
        y_pred = model.predict(X)

        metrics: dict[str, float] = {
            "accuracy": float(accuracy_score(y_true, y_pred)),
            "f1_weighted": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
        }

        # Probability metrics (when supported by the model)
        if hasattr(model, "predict_proba"):
            y_proba = model.predict_proba(X)
            try:
                # log_loss handles binary + multi-class given correct shapes/labels
                metrics["log_loss"] = float(log_loss(y_true, y_proba))
            except Exception:
                # Keep baseline stable; metrics are best-effort
                pass

            try:
                metrics["roc_auc"] = float(self._roc_auc_score(y_true=y_true, y_proba=y_proba))
            except Exception:
                pass

            # Brier score (binary) or multi-class brier (one-vs-rest averaged)
            try:
                metrics["brier_score"] = float(self._brier_score(y_true, y_proba))
            except Exception:
                pass

        return metrics

    def _roc_auc_score(
        self,
        *,
        y_true: NDArray[np.float64],
        y_proba: NDArray[np.float64],
    ) -> float:
        unique = np.unique(y_true)
        if y_proba.ndim != 2:
            raise ValueError("predict_proba must return a 2D array")

        # Binary: assume positive class is column with max proba / or label ordering.
        if len(unique) == 2 and y_proba.shape[1] == 2:
            # Prefer column 1 (sklearn convention), but be robust to label ordering.
            # sklearn convention: for binary classification, predict_proba returns

            # two columns corresponding to the estimator.classes_ ordering.
            # We assume the positive class corresponds to column 1.
            return float(roc_auc_score(y_true, y_proba[:, 1]))

        # Multi-class
        return float(roc_auc_score(y_true, y_proba, multi_class="ovr", average="weighted"))

    def _brier_score(
        self,
        y_true: NDArray[np.float64],
        y_proba: NDArray[np.float64],
    ) -> float:
        unique = np.unique(y_true)
        if len(unique) == 2 and y_proba.shape[1] == 2:
            return float(brier_score_loss(y_true, y_proba[:, 1]))

        # Multi-class: Brier score for one-vs-rest, averaged.
        if not _HAS_LABEL_BINARIZE or label_binarize is None:
            raise RuntimeError("label_binarize unavailable for multi-class brier")
        y_bin = label_binarize(y_true, classes=unique)
        if y_bin.shape[1] != y_proba.shape[1]:
            # Attempt to align by sorting classes
            y_bin = label_binarize(y_true, classes=np.arange(y_proba.shape[1]))
        diff = np.asarray(y_bin, dtype=float) - np.asarray(y_proba, dtype=float)
        return float(np.mean(np.sum(diff**2, axis=1)) / float(y_proba.shape[1]))

    def evaluate_trading(
        self,
        y_pred: NDArray[np.float64],
        prices: NDArray[np.float64],
        horizon: int = 5,
    ) -> dict[str, float]:
        returns = self._compute_strategy_returns(y_pred, prices, horizon)
        sharpe = self._sharpe_ratio(returns)
        max_dd = self._max_drawdown(returns)
        return {
            "sharpe_ratio": float(sharpe),
            "max_drawdown": float(max_dd),
        }

    def _compute_strategy_returns(
        self,
        y_pred: NDArray[np.float64],
        prices: NDArray[np.float64],
        horizon: int,
    ) -> NDArray[np.float64]:
        future_prices = np.roll(prices, -horizon)
        future_prices[-horizon:] = np.nan
        with np.errstate(divide="ignore", invalid="ignore"):
            market_returns = (future_prices - prices) / np.where(prices != 0, prices, np.nan)
        strategy_returns = np.where(y_pred == 1, market_returns, 0.0)
        valid = ~np.isnan(strategy_returns)
        return strategy_returns[valid]

    def _sharpe_ratio(self, returns: NDArray[np.float64]) -> float:
        if returns.size == 0:
            return 0.0
        mean = float(np.mean(returns))
        std = float(np.std(returns))
        if std == 0:
            return 0.0
        return mean / std * np.sqrt(252.0)

    def _max_drawdown(self, returns: NDArray[np.float64]) -> float:
        if returns.size == 0:
            return 0.0
        cumulative = np.cumprod(1.0 + returns)
        peak = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - peak) / np.where(peak == 0, 1.0, peak)
        return float(np.min(drawdown))

    def evaluate(
        self,
        model: Any,
        X: NDArray[np.float64],
        y_true: NDArray[np.float64],
        prices: NDArray[np.float64],
        horizon: int = 5,
    ) -> dict[str, float]:
        classification_metrics = self.evaluate_classification(model, X, y_true)
        y_pred = model.predict(X)
        trading_metrics = self.evaluate_trading(y_pred, prices, horizon)
        return {**classification_metrics, **trading_metrics}

    def evaluate_model(
        self,
        model: Any,
        X: NDArray[np.float64],
        y_true: NDArray[np.float64],
        prices: NDArray[np.float64],
        horizon: int = 5,
    ) -> dict[str, float]:
        try:
            return self.evaluate(model, X, y_true, prices, horizon)
        except Exception as e:
            logger.exception("Model evaluation failed")
            raise ValueError("Evaluation failed") from e
