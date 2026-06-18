# backend/app/schemas/portfolio.py

from __future__ import annotations

from pydantic import BaseModel, PositiveFloat

# NOTE: Avoid using pydantic Field(...) here due to static type-checker overload
# mismatches in the current environment. Runtime validation still occurs via
# constrained types where applicable.


class PortfolioSnapshotResponse(BaseModel):
    """Response model for portfolio snapshot."""

    id: int | None = None
    date: str
    equity: float
    cash: float
    positions: dict[str, dict]  # symbol -> position details


class PortfolioAllocationResponse(BaseModel):
    """Response model for portfolio allocation."""

    allocation: dict[str, float]  # symbol -> percentage
    total_equity: float
    cash: float
    positions_value: float


class TransactionResponse(BaseModel):
    """Response model for transaction."""

    symbol: str
    action: str  # BUY, SELL, DEPOSIT, WITHDRAWAL
    quantity: float
    price: float
    timestamp: str
    fees: float = 0.0


class PortfolioAccountRequest(BaseModel):
    """Request to initialize portfolio account."""

    initial_capital: PositiveFloat = 100000.0


class TradeRequest(BaseModel):
    """Request to execute a trade."""

    symbol: str
    action: str
    quantity: PositiveFloat
    price: PositiveFloat
    fees: float = 0.0

    @classmethod
    def model_validate(cls, obj: object, *args, **kwargs):  # type: ignore[override]
        # Keep runtime validation strict without triggering static Field overload issues
        return super().model_validate(obj, *args, **kwargs)


class AllocationRequest(BaseModel):
    """Request for portfolio allocation optimization."""

    symbols: list[str]
    expected_returns: list[float]
    covariance_matrix: list[list[float]]  # 2D matrix

    method: str = "equal_weight"
    constraints: dict | None = None


class OptimizationResponse(BaseModel):
    """Response from portfolio optimization."""

    weights: dict[str, float]  # symbol -> weight
    expected_return: float
    expected_risk: float
    sharpe_ratio: float
    method: str
    success: bool
    message: str
