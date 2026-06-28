# backend/app/services/portfolio_optimization.py

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import minimize

logger = logging.getLogger(__name__)


@dataclass
class OptimizationConstraints:
    """Constraints for portfolio optimization."""

    long_only: bool = True
    max_weight: float = 1.0
    min_weight: float = 0.0
    target_return: float | None = None
    risk_aversion: float = 1.0  # For mean-variance optimization
    max_sector_exposure: float | None = None  # Max exposure per sector
    sector_map: dict[str, str] | None = None  # symbol -> sector mapping


@dataclass
class OptimizationResult:
    """Result of portfolio optimization."""

    weights: dict[str, float]
    expected_return: float
    expected_risk: float
    sharpe_ratio: float
    method: str
    success: bool
    message: str


class PortfolioOptimizationService:
    """Service for portfolio optimization algorithms."""

    def __init__(self):
        logger.info("PortfolioOptimizationService initialized")

    def equal_weight(self, symbols: list[str]) -> dict[str, float]:
        """Equal weight allocation: allocate equal capital to each asset."""
        if not symbols:
            return {}

        weight = 1.0 / len(symbols)
        return {symbol: weight for symbol in symbols}

    def risk_parity(self, symbols: list[str], covariance_matrix: np.ndarray) -> dict[str, float]:
        """
        Risk parity allocation: allocate based on risk contribution (inverse volatility).
        Assumes equal risk contribution from each asset.
        """
        if not symbols or covariance_matrix.size == 0:
            return {}

        n_assets = len(symbols)
        if n_assets != covariance_matrix.shape[0] or n_assets != covariance_matrix.shape[1]:
            logger.warning("Covariance matrix dimensions don't match number of symbols")
            return self.equal_weight(symbols)

        # Calculate volatilities (square root of diagonal elements)
        volatilities = np.sqrt(np.diag(covariance_matrix))

        # Avoid division by zero
        volatilities = np.where(volatilities == 0, np.inf, volatilities)

        # Inverse volatility weights
        inv_vol = 1.0 / volatilities
        weights = inv_vol / np.sum(inv_vol)

        return dict(zip(symbols, weights, strict=False))

    def mean_variance(
        self,
        expected_returns: np.ndarray,
        covariance_matrix: np.ndarray,
        symbols: list[str],
        constraints: OptimizationConstraints | None = None,
    ) -> OptimizationResult:
        """
        Mean-variance optimization: maximize Sharpe ratio given returns and covariance.
        """
        if constraints is None:
            constraints = OptimizationConstraints()

        n_assets = len(symbols)
        if n_assets == 0:
            return OptimizationResult(
                weights={},
                expected_return=0.0,
                expected_risk=0.0,
                sharpe_ratio=0.0,
                method="mean_variance",
                success=False,
                message="No assets provided",
            )

        # Validate inputs
        if expected_returns.shape[0] != n_assets:
            logger.error("Expected returns length doesn't match number of symbols")
            return OptimizationResult(
                weights={},
                expected_return=0.0,
                expected_risk=0.0,
                sharpe_ratio=0.0,
                method="mean_variance",
                success=False,
                message="Expected returns dimension mismatch",
            )

        if covariance_matrix.shape[0] != n_assets or covariance_matrix.shape[1] != n_assets:
            logger.error("Covariance matrix dimensions don't match number of symbols")
            return OptimizationResult(
                weights={},
                expected_return=0.0,
                expected_risk=0.0,
                sharpe_ratio=0.0,
                method="mean_variance",
                success=False,
                message="Covariance matrix dimension mismatch",
            )

        # Define objective function (negative Sharpe ratio to minimize)
        def objective(weights):
            portfolio_return = np.dot(weights, expected_returns)
            portfolio_variance = np.dot(weights.T, np.dot(covariance_matrix, weights))
            portfolio_std = np.sqrt(portfolio_variance)

            # Avoid division by zero
            if portfolio_std == 0:
                return -float("inf")

            sharpe_ratio = portfolio_return / portfolio_std
            return -sharpe_ratio  # Minimize negative Sharpe ratio

        # Constraints
        constraint_list = []

        # Weights sum to 1
        constraint_list.append({"type": "eq", "fun": lambda x: np.sum(x) - 1})

        # Long-only constraint
        if constraints.long_only:
            for i in range(n_assets):
                constraint_list.append({"type": "ineq", "fun": lambda x, i=i: x[i]})

        # Max weight constraint
        if constraints.max_weight < 1.0:
            for i in range(n_assets):
                constraint_list.append(
                    {"type": "ineq", "fun": lambda x, i=i: constraints.max_weight - x[i]}
                )

        # Min weight constraint
        if constraints.min_weight > 0.0:
            for i in range(n_assets):
                constraint_list.append(
                    {"type": "ineq", "fun": lambda x, i=i: x[i] - constraints.min_weight}
                )

        # Target return constraint
        if constraints.target_return is not None:
            constraint_list.append(
                {
                    "type": "eq",
                    "fun": lambda x: np.dot(x, expected_returns) - constraints.target_return,
                }
            )

        # Sector exposure constraints
        if constraints.max_sector_exposure is not None and constraints.sector_map is not None:
            sectors = set(constraints.sector_map.values())
            for sector in sectors:
                sector_symbols = [s for s, sec in constraints.sector_map.items() if sec == sector]
                if len(sector_symbols) > 1:
                    # Get indices of symbols in this sector
                    sector_indices = [i for i, s in enumerate(symbols) if s in sector_symbols]
                    if sector_indices:
                        constraint_list.append(
                            {
                                "type": "ineq",
                                "fun": lambda x,
                                idx=sector_indices,
                                mse=constraints.max_sector_exposure: (mse - sum(x[i] for i in idx)),
                            }
                        )

        # Bounds for weights
        bounds = [(0.0, 1.0) for _ in range(n_assets)] if constraints.long_only else None

        # Initial guess (equal weights)
        initial_weights = np.array([1.0 / n_assets] * n_assets)

        # Optimize
        try:
            result = minimize(
                objective,
                initial_weights,
                method="SLSQP",
                bounds=bounds,
                constraints=constraint_list,
                options={"ftol": 1e-9, "disp": False},
            )

            if result.success:
                weights = result.x
                portfolio_return = np.dot(weights, expected_returns)
                portfolio_variance = np.dot(weights.T, np.dot(covariance_matrix, weights))
                portfolio_std = np.sqrt(portfolio_variance)
                sharpe_ratio = portfolio_return / portfolio_std if portfolio_std != 0 else 0.0

                return OptimizationResult(
                    weights=dict(zip(symbols, weights, strict=False)),
                    expected_return=float(portfolio_return),
                    expected_risk=float(portfolio_std),
                    sharpe_ratio=float(sharpe_ratio),
                    method="mean_variance",
                    success=True,
                    message="Optimization successful",
                )
            else:
                logger.warning(f"Optimization failed: {result.message}")
                # Fallback to equal weight
                equal_weights = self.equal_weight(symbols)
                portfolio_return = np.dot(list(equal_weights.values()), expected_returns)
                portfolio_variance = np.dot(
                    list(equal_weights.values()),
                    np.dot(covariance_matrix, list(equal_weights.values())),
                )
                portfolio_std = np.sqrt(portfolio_variance)
                sharpe_ratio = portfolio_return / portfolio_std if portfolio_std != 0 else 0.0

                return OptimizationResult(
                    weights=equal_weights,
                    expected_return=float(portfolio_return),
                    expected_risk=float(portfolio_std),
                    sharpe_ratio=float(sharpe_ratio),
                    method="mean_variance_fallback",
                    success=False,
                    message=f"Optimization failed: {result.message}. Falling back to equal weight.",
                )
        except Exception as e:
            logger.error(f"Error during optimization: {e}")
            # Fallback to equal weight
            equal_weights = self.equal_weight(symbols)
            portfolio_return = np.dot(list(equal_weights.values()), expected_returns)
            portfolio_variance = np.dot(
                list(equal_weights.values()),
                np.dot(covariance_matrix, list(equal_weights.values())),
            )
            portfolio_std = np.sqrt(portfolio_variance)
            sharpe_ratio = portfolio_return / portfolio_std if portfolio_std != 0 else 0.0

            return OptimizationResult(
                weights=equal_weights,
                expected_return=float(portfolio_return),
                expected_risk=float(portfolio_std),
                sharpe_ratio=float(sharpe_ratio),
                method="mean_variance_error",
                success=False,
                message=f"Optimization error: {str(e)}. Falling back to equal weight.",
            )


# Global instance for easy access
portfolio_optimization_service = PortfolioOptimizationService()


def optimize_from_signals(
    fused_signals: list[dict[str, Any]],
    symbols: list[str],
    covariance_matrix: np.ndarray,
    max_weight: float = 0.1,
    risk_aversion: float = 1.0,
) -> OptimizationResult:
    """
    Optimize portfolio weights directly from fused signals.

    This is the Phase 10 entry point that takes fused signals + confidence scores
    and produces optimal weights using Sharpe maximization.

    Args:
        fused_signals: List of dicts with 'symbol', 'signal', 'confidence'
        symbols: List of all symbols to consider
        covariance_matrix: Asset covariance matrix
        max_weight: Maximum position size (default 10%)
        risk_aversion: Risk aversion coefficient

    Returns:
        OptimizationResult with weights and risk metrics
    """
    # Build expected returns from signal confidence scores
    signal_returns = {}
    for sig in fused_signals:
        symbol = sig.get("symbol")
        signal = sig.get("signal", "HOLD")
        confidence = sig.get("confidence", 0.5)

        # Map signal to expected return proxy
        if signal == "BUY":
            signal_returns[symbol] = confidence * 0.1  # 0-10% expected return
        elif signal == "SELL":
            signal_returns[symbol] = -confidence * 0.05  # -5% expected return
        else:
            signal_returns[symbol] = 0.0

    expected_returns = np.array([signal_returns.get(s, 0.0) for s in symbols], dtype=np.float64)

    # Use mean-variance optimization with max weight constraint
    constraints = OptimizationConstraints(
        long_only=True,
        max_weight=max_weight,
        min_weight=0.0,
        risk_aversion=risk_aversion,
    )

    return portfolio_optimization_service.mean_variance(
        expected_returns=expected_returns,
        covariance_matrix=covariance_matrix,
        symbols=symbols,
        constraints=constraints,
    )


def aggregate_signals_to_weights(
    fused_signals: list[dict[str, Any]],
    max_weight: float = 0.2,
    covariance_matrix: np.ndarray | None = None,
) -> dict[str, float]:
    """Aggregate fused signals into long-only portfolio weights.

    Bridges the signal-fusion layer to portfolio construction (Priority 3.1):
    only actionable BUY signals receive capital, sized by their confidence.

    When a ``covariance_matrix`` is supplied, mean-variance optimization is used
    (via :func:`optimize_from_signals`). Otherwise weights are confidence-
    proportional, capped at ``max_weight`` and renormalized so they sum to 1.
    Returns an empty dict when there are no actionable BUY signals.
    """
    buys = [s for s in fused_signals if str(s.get("signal", "")).upper() == "BUY"]
    symbols = [str(s.get("symbol")) for s in buys if s.get("symbol")]
    if not symbols:
        return {}

    if covariance_matrix is not None:
        return optimize_from_signals(
            buys, symbols, covariance_matrix, max_weight=max_weight
        ).weights

    raw = {
        str(s["symbol"]): max(0.0, float(s.get("confidence", 0.0))) for s in buys if s.get("symbol")
    }
    total = sum(raw.values())
    if total <= 0:
        # No usable confidence: fall back to equal weight (still capped).
        weights = {sym: 1.0 / len(symbols) for sym in symbols}
    else:
        weights = {sym: v / total for sym, v in raw.items()}

    # Apply the per-position cap, then renormalize the remaining (uncapped) names
    # so the book stays fully invested where possible.
    for _ in range(len(weights)):
        over = {s: w for s, w in weights.items() if w > max_weight + 1e-12}
        if not over:
            break
        excess = sum(w - max_weight for w in over.values())
        for s in over:
            weights[s] = max_weight
        free = {s: w for s, w in weights.items() if w < max_weight - 1e-12}
        free_total = sum(free.values())
        if free_total <= 0:
            break
        for s in free:
            weights[s] += excess * (weights[s] / free_total)

    return weights
