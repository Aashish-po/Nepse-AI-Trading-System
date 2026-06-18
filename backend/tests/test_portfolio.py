# backend/tests/test_portfolio.py

from decimal import Decimal

import numpy as np
from app.services.portfolio_account import PortfolioAccountService
from app.services.portfolio_optimization import (
    OptimizationConstraints,
    PortfolioOptimizationService,
)


def test_portfolio_account_initialization():
    """Test portfolio account initialization."""
    portfolio = PortfolioAccountService(Decimal("50000.00"))
    assert portfolio.initial_capital == Decimal("50000.00")
    assert portfolio.cash == Decimal("50000.00")
    assert len(portfolio.positions) == 0
    assert len(portfolio.transactions) == 0


def test_portfolio_deposit():
    """Test depositing funds."""
    portfolio = PortfolioAccountService()
    initial_cash = portfolio.cash

    portfolio.deposit(Decimal("10000.00"))

    assert portfolio.cash == initial_cash + Decimal("10000.00")
    assert len(portfolio.transactions) == 1
    assert portfolio.transactions[0].action == "DEPOSIT"


def test_portfolio_withdraw():
    """Test withdrawing funds."""
    portfolio = PortfolioAccountService(Decimal("10000.00"))
    initial_cash = portfolio.cash

    portfolio.withdraw(Decimal("3000.00"))

    assert portfolio.cash == initial_cash - Decimal("3000.00")
    assert len(portfolio.transactions) == 1
    assert portfolio.transactions[0].action == "WITHDRAWAL"


def test_portfolio_buy_stock():
    """Test buying a stock."""
    portfolio = PortfolioAccountService(Decimal("10000.00"))

    # Buy 10 shares at $100 each
    success = portfolio.buy("ABC", Decimal("10"), Decimal("100.00"))

    assert success
    assert portfolio.cash == Decimal("9000.00")  # 10000 - (10*100)
    assert "ABC" in portfolio.positions
    assert portfolio.positions["ABC"].quantity == Decimal("10")
    assert portfolio.positions["ABC"].average_price == Decimal("100.00")
    assert len(portfolio.transactions) == 1
    assert portfolio.transactions[0].action == "BUY"


def test_portfolio_sell_stock():
    """Test selling a stock."""
    portfolio = PortfolioAccountService(Decimal("10000.00"))

    # First buy some stock
    portfolio.buy("ABC", Decimal("10"), Decimal("100.00"))

    # Then sell 5 shares
    success = portfolio.sell("ABC", Decimal("5"), Decimal("110.00"))

    assert success
    assert portfolio.positions["ABC"].quantity == Decimal("5")
    # Cash should be: 10000 - (10*100) + (5*110) = 10000 - 1000 + 550 = 9550
    assert portfolio.cash == Decimal("9550.00")
    assert len(portfolio.transactions) == 2
    assert portfolio.transactions[1].action == "SELL"


def test_portfolio_insufficient_funds():
    """Test buying with insufficient funds."""
    portfolio = PortfolioAccountService(Decimal("1000.00"))

    # Try to buy stock worth more than cash
    success = portfolio.buy("ABC", Decimal("20"), Decimal("100.00"))  # 2000 > 1000

    assert not success
    assert portfolio.cash == Decimal("1000.00")  # Unchanged
    assert len(portfolio.positions) == 0
    assert len(portfolio.transactions) == 0


def test_portfolio_sell_insufficient_shares():
    """Test selling more shares than owned."""
    portfolio = PortfolioAccountService(Decimal("10000.00"))

    # Buy 5 shares
    portfolio.buy("ABC", Decimal("5"), Decimal("100.00"))

    # Try to sell 10 shares (more than owned)
    success = portfolio.sell("ABC", Decimal("10"), Decimal("110.00"))

    assert not success
    assert portfolio.positions["ABC"].quantity == Decimal("5")  # Unchanged
    assert len(portfolio.transactions) == 1  # Only the buy transaction


def test_portfolio_snapshot():
    """Test portfolio snapshot generation."""
    portfolio = PortfolioAccountService(Decimal("10000.00"))

    # Buy some stock
    portfolio.buy("ABC", Decimal("10"), Decimal("100.00"))
    portfolio.buy("XYZ", Decimal("5"), Decimal("200.00"))

    snapshot = portfolio.get_portfolio_snapshot()

    assert snapshot.equity == Decimal("10000.00")  # No change in equity yet
    assert snapshot.cash == Decimal("8000.00")  # 10000 - (10*100) - (5*200)
    assert len(snapshot.positions) == 2
    assert "ABC" in snapshot.positions
    assert "XYZ" in snapshot.positions


def test_portfolio_allocation():
    """Test portfolio allocation calculation."""
    portfolio = PortfolioAccountService(Decimal("10000.00"))

    # Buy some stock
    portfolio.buy("ABC", Decimal("10"), Decimal("100.00"))  # $1000
    portfolio.buy("XYZ", Decimal("20"), Decimal("150.00"))  # $3000

    # Cash: 10000 - 1000 - 3000 = 6000
    # Total equity: 6000 + 1000 + 3000 = 10000
    # Allocation: CASH 60%, ABC 10%, XYZ 30%

    allocation = portfolio.get_allocation()

    assert abs(allocation["CASH"] - 60.0) < 0.01
    assert abs(allocation["ABC"] - 10.0) < 0.01
    assert abs(allocation["XYZ"] - 30.0) < 0.01


def test_equal_weight_allocation():
    """Test equal weight allocation."""
    opt_service = PortfolioOptimizationService()
    symbols = ["AAPL", "GOOGL", "MSFT", "AMZN"]

    weights = opt_service.equal_weight(symbols)

    assert len(weights) == 4
    for symbol in symbols:
        assert abs(weights[symbol] - 0.25) < 0.0001


def test_risk_parity_allocation():
    """Test risk parity allocation."""
    opt_service = PortfolioOptimizationService()
    symbols = ["AAPL", "GOOGL"]

    # Simple covariance matrix (2x2)
    # AAPL volatility: 0.2, GOOGL volatility: 0.3
    # Covariance: 0.1
    covariance_matrix = np.array(
        [
            [0.04, 0.1],  # 0.2^2 = 0.04
            [0.1, 0.09],  # 0.3^2 = 0.09
        ]
    )

    weights = opt_service.risk_parity(symbols, covariance_matrix)

    assert len(weights) == 2
    # Risk parity should give higher weight to lower volatility asset (AAPL)
    assert weights["AAPL"] > weights["GOOGL"]
    # Weights should sum to 1
    assert abs(sum(weights.values()) - 1.0) < 0.0001


def test_mean_variance_optimization():
    """Test mean-variance optimization."""
    opt_service = PortfolioOptimizationService()
    symbols = ["AAPL", "GOOGL"]

    # Expected returns: AAPL 0.15, GOOGL 0.12
    expected_returns = np.array([0.15, 0.12])

    # Covariance matrix
    covariance_matrix = np.array([[0.04, 0.01], [0.01, 0.09]])

    constraints = OptimizationConstraints(long_only=True, max_weight=0.8)

    result = opt_service.mean_variance(
        expected_returns=expected_returns,
        covariance_matrix=covariance_matrix,
        symbols=symbols,
        constraints=constraints,
    )

    assert result.success
    assert len(result.weights) == 2
    # Weights should sum to 1
    assert abs(sum(result.weights.values()) - 1.0) < 0.0001
    # All weights should be between 0 and 1 (long_only, max_weight=0.8)
    for weight in result.weights.values():
        assert 0 <= weight <= 0.8 + 0.0001  # Small tolerance for floating point
