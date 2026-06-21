"""Small factor analysis helpers based on PCA."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class FactorResult:
    factors: np.ndarray
    loadings: np.ndarray
    explained_variance: np.ndarray


class FactorAnalysisService:
    def compute_factors(self, returns: np.ndarray, n_factors: int = 3) -> FactorResult:
        if returns.ndim != 2:
            raise ValueError("returns must be a 2D array")
        centered = returns - returns.mean(axis=0, keepdims=True)
        u, s, vt = np.linalg.svd(centered, full_matrices=False)
        k = min(n_factors, vt.shape[0])
        factors = u[:, :k] * s[:k]
        loadings = vt[:k, :].T
        explained = (s[:k] ** 2) / np.sum(s**2) if np.sum(s**2) else np.zeros(k)
        return FactorResult(factors=factors, loadings=loadings, explained_variance=explained)

    def factor_exposure(self, loadings: np.ndarray, symbols: list[str]) -> dict[str, list[float]]:
        if loadings.shape[0] != len(symbols):
            raise ValueError("loadings row count must match symbols")
        return {symbol: loadings[i].tolist() for i, symbol in enumerate(symbols)}

    def factor_attribution(
        self, exposures: dict[str, list[float]], factor_returns: list[float]
    ) -> dict[str, float]:
        factor_array = np.array(factor_returns, dtype=float)
        return {
            symbol: float(np.dot(np.array(weights, dtype=float), factor_array))
            for symbol, weights in exposures.items()
        }
