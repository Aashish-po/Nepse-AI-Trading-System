"""Model evaluation for classification and trading metrics."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
from numpy.typing import NDArray
from sklearn.metrics import accuracy_score, f1_score
from sqlalchemy.orm import Session

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
        return {
            "accuracy": float(accuracy_score(y_true, y_pred)),
            "f1_weighted": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
        }

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
