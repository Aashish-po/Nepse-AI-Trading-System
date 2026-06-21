# backend/tests/test_portfolio_integration_p3.py
"""Priority 3: signal -> portfolio weights aggregation and rebalance drift detection."""

from decimal import Decimal

import numpy as np
from app.services.portfolio_account import PortfolioAccountService
from app.services.portfolio_optimization import aggregate_signals_to_weights


# --------------------------------------------------- aggregate_signals_to_weights
def test_aggregate_only_buys_get_weight():
    signals = [
        {"symbol": "AAA", "signal": "BUY", "confidence": 0.8},
        {"symbol": "BBB", "signal": "SELL", "confidence": 0.9},
        {"symbol": "CCC", "signal": "HOLD", "confidence": 0.7},
    ]
    weights = aggregate_signals_to_weights(signals, max_weight=1.0)

    assert set(weights) == {"AAA"}
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_aggregate_confidence_proportional():
    signals = [
        {"symbol": "AAA", "signal": "BUY", "confidence": 0.6},
        {"symbol": "BBB", "signal": "BUY", "confidence": 0.2},
    ]
    weights = aggregate_signals_to_weights(signals, max_weight=1.0)

    # 0.6 / 0.8 = 0.75, 0.2 / 0.8 = 0.25
    assert abs(weights["AAA"] - 0.75) < 1e-9
    assert abs(weights["BBB"] - 0.25) < 1e-9


def test_aggregate_respects_max_weight_cap():
    signals = [
        {"symbol": "AAA", "signal": "BUY", "confidence": 0.95},
        {"symbol": "BBB", "signal": "BUY", "confidence": 0.05},
    ]
    weights = aggregate_signals_to_weights(signals, max_weight=0.6)

    assert weights["AAA"] <= 0.6 + 1e-9
    # Excess redistributed to BBB; still fully invested.
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_aggregate_no_buys_returns_empty():
    signals = [{"symbol": "AAA", "signal": "HOLD", "confidence": 0.5}]
    assert aggregate_signals_to_weights(signals) == {}


def test_aggregate_zero_confidence_falls_back_to_equal_weight():
    signals = [
        {"symbol": "AAA", "signal": "BUY", "confidence": 0.0},
        {"symbol": "BBB", "signal": "BUY", "confidence": 0.0},
    ]
    weights = aggregate_signals_to_weights(signals, max_weight=1.0)
    assert abs(weights["AAA"] - 0.5) < 1e-9
    assert abs(weights["BBB"] - 0.5) < 1e-9


def test_aggregate_with_covariance_uses_mean_variance():
    signals = [
        {"symbol": "AAA", "signal": "BUY", "confidence": 0.8},
        {"symbol": "BBB", "signal": "BUY", "confidence": 0.6},
    ]
    cov = np.array([[0.04, 0.01], [0.01, 0.09]])
    weights = aggregate_signals_to_weights(signals, max_weight=0.8, covariance_matrix=cov)

    assert set(weights) == {"AAA", "BBB"}
    assert abs(sum(weights.values()) - 1.0) < 1e-6


# ------------------------------------------------------ rebalance drift detection
def _funded_portfolio() -> PortfolioAccountService:
    p = PortfolioAccountService(Decimal("10000.00"))
    p.buy("AAA", Decimal("40"), Decimal("100.00"))  # 4000 -> 40%
    p.buy("BBB", Decimal("20"), Decimal("100.00"))  # 2000 -> 20%
    # cash 4000 -> 40%
    return p


def test_get_weights_excludes_cash():
    p = _funded_portfolio()
    weights = p.get_weights()
    assert abs(weights["AAA"] - 0.4) < 1e-9
    assert abs(weights["BBB"] - 0.2) < 1e-9
    assert "CASH" not in weights


def test_compute_drift_includes_exited_targets():
    p = _funded_portfolio()
    # Target wants AAA at 40% (no drift) but a brand new CCC at 30%.
    drift = p.compute_drift({"AAA": 0.4, "CCC": 0.3})
    assert abs(drift["AAA"]) < 1e-9
    assert abs(drift["CCC"] - 0.3) < 1e-9
    # BBB present in portfolio but not target -> drifts by its full weight.
    assert abs(drift["BBB"] - 0.2) < 1e-9


def test_should_rebalance_true_when_drift_exceeds_threshold():
    p = _funded_portfolio()
    # AAA target 50% vs current 40% -> 10% drift > 5% threshold.
    assert p.should_rebalance({"AAA": 0.5, "BBB": 0.2}, threshold=0.05) is True


def test_should_rebalance_false_within_threshold():
    p = _funded_portfolio()
    # All within 5%.
    assert p.should_rebalance({"AAA": 0.42, "BBB": 0.18}, threshold=0.05) is False


def test_should_rebalance_false_for_empty_portfolio():
    p = PortfolioAccountService(Decimal("10000.00"))
    assert p.should_rebalance({}, threshold=0.05) is False
