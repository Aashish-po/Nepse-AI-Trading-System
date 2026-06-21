# backend/app/schemas/paper_trading.py

from __future__ import annotations

from pydantic import BaseModel, PositiveFloat

# NOTE: Mirrors the style of schemas/portfolio.py — constrained scalar types
# instead of pydantic Field(...) to avoid static type-checker overload issues.


class CreateAccountRequest(BaseModel):
    """Request to create a paper trading account."""

    name: str = "Paper Account"
    initial_capital: PositiveFloat = 1000000.0


class OrderRequest(BaseModel):
    """Request to submit a paper order.

    ``market_price`` and ``volume`` are optional; when omitted the API fetches
    the latest close/volume for the symbol from the price history.
    """

    symbol: str
    side: str  # BUY or SELL
    quantity: PositiveFloat
    order_type: str = "MARKET"  # MARKET or LIMIT
    limit_price: float | None = None
    market_price: float | None = None
    volume: int | None = None


class OrderResponse(BaseModel):
    """Response describing a submitted order's execution outcome."""

    id: int
    account_id: int
    symbol: str
    side: str
    order_type: str
    status: str
    requested_quantity: float
    filled_quantity: float
    limit_price: float | None = None
    fill_price: float | None = None
    commission: float
    slippage_cost: float
    realized_pnl: float
    timestamp: str
    message: str


class AccountSummaryResponse(BaseModel):
    """Response with current account state and P&L."""

    account_id: int
    name: str
    created_at: str
    initial_capital: float
    cash: float
    positions_value: float
    equity: float
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    total_return_pct: float
    open_positions: int
    order_count: int
    equity_curve: list[dict]
    positions: dict[str, dict]


class AccountListItem(BaseModel):
    """Lightweight account summary for listings."""

    account_id: int
    name: str
    equity: float
    created_at: str
