"""Volatility, VaR, and CVaR helpers for risk assessment."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import norm


@dataclass(frozen=True)
class RiskForecast:
    horizon_days: int
    mean_return: float
    ewma_volatility: float
    garch_volatility: float
    var_95: float
    var_99: float
    cvar_95: float
    cvar_99: float


class RiskModel:
    """Estimate short-horizon volatility and tail risk from return series."""

    def __init__(
        self,
        alpha: float = 0.08,
        beta: float = 0.90,
        long_run_weight: float = 0.02,
    ) -> None:
        if alpha < 0 or beta < 0 or alpha + beta >= 1:
            raise ValueError("Require 0 <= alpha, beta and alpha + beta < 1")
        self.alpha = alpha
        self.beta = beta
        self.long_run_weight = long_run_weight
        self._returns: np.ndarray | None = None
        self._ewma_sigma: float | None = None
        self._garch_sigma: float | None = None

    def fit(self, returns: Sequence[float] | np.ndarray | pd.Series) -> RiskModel:
        series = np.asarray(returns, dtype=np.float64)
        if series.size < 5:
            raise ValueError("Need at least 5 returns to fit risk model")
        series = series[np.isfinite(series)]
        if series.size < 5:
            raise ValueError("Need finite returns to fit risk model")

        self._returns = series
        self._ewma_sigma = self._compute_ewma_sigma(series)
        self._garch_sigma = self._compute_garch_sigma(series)
        return self

    def forecast(self, horizon_days: int = 1) -> RiskForecast:
        if self._returns is None or self._ewma_sigma is None or self._garch_sigma is None:
            raise ValueError("Model must be fit before forecasting")

        mean_return = float(np.mean(self._returns))
        horizon_scale = float(np.sqrt(max(horizon_days, 1)))
        ewma_sigma = self._ewma_sigma * horizon_scale
        garch_sigma = self._garch_sigma * horizon_scale

        var_95 = self._var_from_normal(mean_return, garch_sigma, 0.95)
        var_99 = self._var_from_normal(mean_return, garch_sigma, 0.99)
        cvar_95 = self._cvar_from_normal(mean_return, garch_sigma, 0.95)
        cvar_99 = self._cvar_from_normal(mean_return, garch_sigma, 0.99)

        return RiskForecast(
            horizon_days=horizon_days,
            mean_return=mean_return,
            ewma_volatility=ewma_sigma,
            garch_volatility=garch_sigma,
            var_95=var_95,
            var_99=var_99,
            cvar_95=cvar_95,
            cvar_99=cvar_99,
        )

    def to_risk_assessment(self, forecast: RiskForecast) -> dict[str, float | int | str]:
        """Translate the forecast into a simple advisory risk assessment."""
        if forecast.var_99 <= -0.05 or forecast.garch_volatility >= 0.05:
            action = "HOLD_ONLY"
            state = "critical"
        elif forecast.var_95 <= -0.02 or forecast.garch_volatility >= 0.03:
            action = "REDUCE"
            state = "elevated"
        else:
            action = "NORMAL"
            state = "normal"

        return {
            "status": state,
            "action": action,
            "horizon_days": forecast.horizon_days,
            "mean_return": forecast.mean_return,
            "ewma_volatility": forecast.ewma_volatility,
            "garch_volatility": forecast.garch_volatility,
            "var_95": forecast.var_95,
            "var_99": forecast.var_99,
            "cvar_95": forecast.cvar_95,
            "cvar_99": forecast.cvar_99,
        }

    def _compute_ewma_sigma(self, returns: np.ndarray) -> float:
        variance = float(np.var(returns, ddof=1))
        for value in returns:
            variance = (
                self.long_run_weight * variance
                + self.alpha * float(value) ** 2
                + self.beta * variance
            )
        return float(np.sqrt(max(variance, 0.0)))

    def _compute_garch_sigma(self, returns: np.ndarray) -> float:
        long_run_variance = float(np.var(returns, ddof=1))
        if long_run_variance <= 0:
            long_run_variance = 1e-8
        omega = long_run_variance * (1.0 - self.alpha - self.beta)
        variance = long_run_variance
        for value in returns:
            variance = omega + self.alpha * float(value) ** 2 + self.beta * variance
        return float(np.sqrt(max(variance, 0.0)))

    def _var_from_normal(self, mean_return: float, sigma: float, confidence: float) -> float:
        tail_probability = 1.0 - confidence
        z_score = norm.ppf(tail_probability)
        return float(mean_return + sigma * z_score)

    def _cvar_from_normal(self, mean_return: float, sigma: float, confidence: float) -> float:
        tail_probability = 1.0 - confidence
        z_score = norm.ppf(tail_probability)
        tail_density = norm.pdf(z_score)
        return float(mean_return - sigma * tail_density / tail_probability)
