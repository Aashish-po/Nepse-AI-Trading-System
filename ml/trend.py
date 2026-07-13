"""Trend classification helpers for aggregated market/index features."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

TREND_REGIMES = ("bear", "sideways", "bull")


@dataclass(frozen=True)
class TrendFeatureSet:
    mean_return: float
    volatility: float
    momentum_5: float
    momentum_20: float
    breadth: float
    drawdown: float


def build_trend_features(frame: pd.DataFrame, price_column: str = "index_close") -> pd.DataFrame:
    """Build point-in-time market regime features from an index time series.

    The returned frame is aligned row-for-row with the input after dropping the first
    NaN return row; callers can pair it with regime labels generated from the same
    source series.
    """
    if price_column not in frame.columns:
        raise KeyError(f"Missing required price column: {price_column}")

    prices = pd.Series(frame[price_column], dtype="float64").reset_index(drop=True)
    returns = prices.pct_change().fillna(0.0)

    rolling_5 = returns.rolling(5, min_periods=1)
    rolling_20 = returns.rolling(20, min_periods=1)
    cumulative_peak = prices.cummax().replace(0, np.nan)
    drawdown = (prices - cumulative_peak) / cumulative_peak

    feature_frame = pd.DataFrame(
        {
            "mean_return": rolling_20.mean(),
            "volatility": rolling_20.std(ddof=0).fillna(0.0),
            "momentum_5": prices.pct_change(5).fillna(0.0),
            "momentum_20": prices.pct_change(20).fillna(0.0),
            "breadth": rolling_5.mean().fillna(0.0),
            "drawdown": drawdown.fillna(0.0),
        }
    )
    return feature_frame.replace([np.inf, -np.inf], 0.0).fillna(0.0)


def regime_from_returns(
    returns: Sequence[float] | np.ndarray | pd.Series,
    bull_threshold: float = 0.002,
    bear_threshold: float = -0.002,
) -> list[str]:
    """Derive a simple regime label series from returns for training/smoke tests."""
    labels: list[str] = []
    for value in returns:
        if value >= bull_threshold:
            labels.append("bull")
        elif value <= bear_threshold:
            labels.append("bear")
        else:
            labels.append("sideways")
    return labels


class TrendAnalyzer:
    """Regime classifier over index-level features."""

    def __init__(self, random_state: int = 42, n_estimators: int = 200) -> None:
        self.random_state = random_state
        self.model = RandomForestClassifier(
            random_state=random_state,
            n_estimators=n_estimators,
            class_weight="balanced_subsample",
        )
        self._feature_columns = [
            "mean_return",
            "volatility",
            "momentum_5",
            "momentum_20",
            "breadth",
            "drawdown",
        ]

    def fit(self, features: pd.DataFrame, regimes: Sequence[str]) -> TrendAnalyzer:
        X = self._prepare_frame(features)
        y = pd.Series(list(regimes), dtype="string")
        if len(X) != len(y):
            raise ValueError("Feature and regime lengths must match")
        self.model.fit(X, y)
        return self

    def predict(self, features: pd.DataFrame) -> list[str]:
        X = self._prepare_frame(features)
        return [str(value) for value in self.model.predict(X)]

    def predict_regime(self, features: pd.DataFrame) -> str:
        return self.predict(features)[-1]

    def predict_proba(self, features: pd.DataFrame) -> dict[str, float]:
        X = self._prepare_frame(features)
        probabilities = self.model.predict_proba(X)[-1]
        return {
            str(label): float(probability)
            for label, probability in zip(self.model.classes_, probabilities, strict=False)
        }

    def fit_from_prices(
        self, frame: pd.DataFrame, price_column: str = "index_close"
    ) -> TrendAnalyzer:
        features = build_trend_features(frame, price_column=price_column)
        prices = pd.Series(frame[price_column], dtype="float64").reset_index(drop=True)
        returns = prices.pct_change().fillna(0.0).tolist()
        regimes = regime_from_returns(returns)
        return self.fit(features, regimes)

    def _prepare_frame(self, features: pd.DataFrame) -> pd.DataFrame:
        missing = [column for column in self._feature_columns if column not in features.columns]
        if missing:
            raise KeyError(f"Missing required trend features: {missing}")
        prepared = features[self._feature_columns].astype(float).replace([np.inf, -np.inf], 0.0)
        return prepared.fillna(0.0)
