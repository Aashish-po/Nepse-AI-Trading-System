"""Portfolio optimization and account management API routes."""

import logging
from decimal import Decimal

import numpy as np
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.portfolio import (
    AllocationRequest,
    OptimizationResponse,
    PortfolioAccountRequest,
    PortfolioAllocationResponse,
    PortfolioSnapshotResponse,
    TradeRequest,
    TransactionResponse,
)
from app.services.portfolio_account import PortfolioAccountService, Position
from app.services.portfolio_optimization import (
    OptimizationConstraints,
    portfolio_optimization_service,
)
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

# In-memory storage for portfolio accounts (in production, this would be in database)
# For simplicity, we'll store one portfolio per user session
_portfolio_accounts: dict[str, PortfolioAccountService] = {}


def _get_or_create_portfolio_account(user_id: str) -> PortfolioAccountService:
    """Get or create portfolio account for a user."""
    if user_id not in _portfolio_accounts:
        _portfolio_accounts[user_id] = PortfolioAccountService()
        logger.info(f"Created new portfolio account for user {user_id}")
    return _portfolio_accounts[user_id]


def _position_to_dict(position: Position) -> dict:
    """Convert Position object to dictionary for JSON serialization."""
    return {
        "symbol": position.symbol,
        "quantity": float(position.quantity),
        "average_price": float(position.average_price),
        "current_price": float(position.current_price) if position.current_price else None,
        "market_value": float(position.market_value),
        "unrealized_pnl": float(position.unrealized_pnl),
    }


@router.post("/account", response_model=dict)
def create_portfolio_account(
    request: PortfolioAccountRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create or reset portfolio account for the user."""
    initial_capital = Decimal(str(request.initial_capital)) if request else Decimal("100000.00")
    portfolio_account = PortfolioAccountService(initial_capital=initial_capital)
    _portfolio_accounts[user.id] = portfolio_account

    logger.info(f"Created portfolio account for user {user.id} with capital {initial_capital}")
    return {
        "message": "Portfolio account created successfully",
        "initial_capital": float(initial_capital),
        "user_id": user.id,
    }


@router.get("/account/snapshot", response_model=PortfolioSnapshotResponse)
def get_portfolio_snapshot(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current portfolio snapshot."""
    portfolio_account = _get_or_create_portfolio_account(user.id)
    snapshot = portfolio_account.get_portfolio_snapshot()

    return PortfolioSnapshotResponse(
        id=snapshot.id,
        date=snapshot.date.isoformat(),
        equity=float(snapshot.equity),
        cash=float(snapshot.cash),
        positions={symbol: _position_to_dict(pos) for symbol, pos in snapshot.positions.items()},
    )


@router.get("/account/allocation", response_model=PortfolioAllocationResponse)
def get_portfolio_allocation(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current portfolio allocation."""
    portfolio_account = _get_or_create_portfolio_account(user.id)
    allocation = portfolio_account.get_allocation()
    total_equity = float(portfolio_account.get_total_equity())
    cash = float(portfolio_account.cash)

    # Calculate positions value
    positions_value = total_equity - cash

    return PortfolioAllocationResponse(
        allocation=allocation, total_equity=total_equity, cash=cash, positions_value=positions_value
    )


@router.get("/account/transactions", response_model=list[TransactionResponse])
def get_transaction_history(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=1000),
):
    """Get transaction history."""
    portfolio_account = _get_or_create_portfolio_account(user.id)
    transactions = portfolio_account.get_transaction_history()

    # Return most recent transactions first, limited by count
    recent_transactions = list(reversed(transactions))[:limit]

    return [
        TransactionResponse(
            symbol=t.symbol,
            action=t.action,
            quantity=float(t.quantity),
            price=float(t.price),
            timestamp=t.timestamp.isoformat(),
            fees=float(t.fees),
        )
        for t in recent_transactions
    ]


@router.post("/account/trade", response_model=dict)
def execute_trade(
    request: TradeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Execute a buy or sell trade."""
    portfolio_account = _get_or_create_portfolio_account(user.id)

    # Convert to Decimal for precision
    quantity = Decimal(str(request.quantity))
    price = Decimal(str(request.price))
    fees = Decimal(str(request.fees))

    success = False
    if request.action.upper() == "BUY":
        success = portfolio_account.buy(
            symbol=request.symbol.upper(), quantity=quantity, price=price, fees=fees
        )
    elif request.action.upper() == "SELL":
        success = portfolio_account.sell(
            symbol=request.symbol.upper(), quantity=quantity, price=price, fees=fees
        )

    if not success:
        raise HTTPException(
            status_code=400, detail=f"Failed to execute {request.action} trade for {request.symbol}"
        )

    return {
        "message": f"{request.action} order executed successfully",
        "symbol": request.symbol.upper(),
        "quantity": float(quantity),
        "price": float(price),
        "fees": float(fees),
        "total_value": float(quantity * price),
        "new_cash_balance": float(portfolio_account.cash),
    }


@router.post("/optimize", response_model=OptimizationResponse)
def optimize_portfolio(
    request: AllocationRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Optimize portfolio allocation using various methods."""
    try:
        # Convert inputs to numpy arrays
        expected_returns = np.array(request.expected_returns)
        covariance_matrix = np.array(request.covariance_matrix)

        # Validate dimensions
        n_symbols = len(request.symbols)
        if len(expected_returns) != n_symbols:
            raise ValueError("Length of expected_returns must match number of symbols")
        if covariance_matrix.shape != (n_symbols, n_symbols):
            raise ValueError("Covariance matrix must be square and match number of symbols")

        # Execute optimization based on method
        if request.method == "equal_weight":
            weights = portfolio_optimization_service.equal_weight(request.symbols)
            # Calculate portfolio metrics
            portfolio_return = np.dot(list(weights.values()), expected_returns)
            portfolio_variance = np.dot(
                list(weights.values()), np.dot(covariance_matrix, list(weights.values()))
            )
            portfolio_std = np.sqrt(portfolio_variance)
            sharpe_ratio = portfolio_return / portfolio_std if portfolio_std != 0 else 0.0

            return OptimizationResponse(
                weights=weights,
                expected_return=float(portfolio_return),
                expected_risk=float(portfolio_std),
                sharpe_ratio=float(sharpe_ratio),
                method="equal_weight",
                success=True,
                message="Equal weight allocation calculated",
            )

        elif request.method == "risk_parity":
            weights = portfolio_optimization_service.risk_parity(request.symbols, covariance_matrix)
            # Calculate portfolio metrics
            portfolio_return = np.dot(list(weights.values()), expected_returns)
            portfolio_variance = np.dot(
                list(weights.values()), np.dot(covariance_matrix, list(weights.values()))
            )
            portfolio_std = np.sqrt(portfolio_variance)
            sharpe_ratio = portfolio_return / portfolio_std if portfolio_std != 0 else 0.0

            return OptimizationResponse(
                weights=weights,
                expected_return=float(portfolio_return),
                expected_risk=float(portfolio_std),
                sharpe_ratio=float(sharpe_ratio),
                method="risk_parity",
                success=True,
                message="Risk parity allocation calculated",
            )

        elif request.method == "mean_variance":
            # Parse constraints if provided
            constraints = OptimizationConstraints()
            if request.constraints:
                if "long_only" in request.constraints:
                    constraints.long_only = request.constraints["long_only"]
                if "max_weight" in request.constraints:
                    constraints.max_weight = request.constraints["max_weight"]
                if "min_weight" in request.constraints:
                    constraints.min_weight = request.constraints["min_weight"]
                if "target_return" in request.constraints:
                    constraints.target_return = request.constraints["target_return"]
                if "risk_aversion" in request.constraints:
                    constraints.risk_aversion = request.constraints["risk_aversion"]

            result = portfolio_optimization_service.mean_variance(
                expected_returns=expected_returns,
                covariance_matrix=covariance_matrix,
                symbols=request.symbols,
                constraints=constraints,
            )

            return OptimizationResponse(
                weights=result.weights,
                expected_return=result.expected_return,
                expected_risk=result.expected_risk,
                sharpe_ratio=result.sharpe_ratio,
                method=result.method,
                success=result.success,
                message=result.message,
            )

        else:
            raise ValueError(f"Unknown optimization method: {request.method}")

    except Exception as e:
        logger.error(f"Error in portfolio optimization: {e}")
        raise HTTPException(
            status_code=400, detail=f"Portfolio optimization failed: {str(e)}"
        ) from e


# Health check endpoint
@router.get("/health")
def portfolio_health_check():
    """Health check for portfolio service."""
    return {"status": "healthy", "service": "portfolio", "version": "1.0.0"}
