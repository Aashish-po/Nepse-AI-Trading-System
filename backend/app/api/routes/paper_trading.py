"""Paper trading API routes.

Exposes the in-memory :class:`PaperTradingEngine` over REST. Accounts are shared
process-wide (single-node deployment); a DB-backed store would be needed for
horizontal scaling. Market prices for orders are sourced from the price history
when the client does not supply them explicitly.
"""

import logging
from decimal import Decimal

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.price import Price
from app.models.stock import Stock
from app.models.user import User
from app.schemas.paper_trading import (
    AccountListItem,
    AccountSummaryResponse,
    CreateAccountRequest,
    OrderRequest,
    OrderResponse,
)
from app.services.paper_trading import PaperOrder, paper_trading_engine
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/paper-trading", tags=["paper-trading"])


def _order_to_response(order: PaperOrder) -> OrderResponse:
    return OrderResponse(
        id=order.id,
        account_id=order.account_id,
        symbol=order.symbol,
        side=order.side.value,
        order_type=order.order_type.value,
        status=order.status.value,
        requested_quantity=float(order.requested_quantity),
        filled_quantity=float(order.filled_quantity),
        limit_price=float(order.limit_price) if order.limit_price is not None else None,
        fill_price=float(order.fill_price) if order.fill_price is not None else None,
        commission=float(order.commission),
        slippage_cost=float(order.slippage_cost),
        realized_pnl=float(order.realized_pnl),
        timestamp=order.timestamp.isoformat(),
        message=order.message,
    )


def _latest_price(db: Session, symbol: str) -> tuple[Decimal, int | None] | None:
    """Return the latest (close, volume) for a symbol, or None if unavailable."""
    row = (
        db.query(Price)
        .join(Stock, Price.stock_id == Stock.id)
        .filter(Stock.symbol == symbol.upper())
        .filter(Price.close.isnot(None))
        .order_by(Price.date.desc())
        .first()
    )
    if row is None or row.close is None:
        return None
    return Decimal(str(row.close)), row.volume


@router.post("/accounts", response_model=AccountSummaryResponse)
def create_account(
    request: CreateAccountRequest | None = None,
    user: User = Depends(get_current_user),
):
    """Create a new paper trading account."""
    req = request or CreateAccountRequest()
    account = paper_trading_engine.create_account(
        name=req.name, initial_capital=Decimal(str(req.initial_capital))
    )
    logger.info("User %s created paper account %s", user.id, account.id)
    return AccountSummaryResponse(**paper_trading_engine.get_account_summary(account.id))


@router.get("/accounts", response_model=list[AccountListItem])
def list_accounts(user: User = Depends(get_current_user)):
    """List all paper trading accounts."""
    return [
        AccountListItem(
            account_id=a.id,
            name=a.name,
            equity=float(a.equity()),
            created_at=a.created_at.isoformat(),
        )
        for a in paper_trading_engine.list_accounts()
    ]


@router.get("/accounts/{account_id}/summary", response_model=AccountSummaryResponse)
def get_summary(account_id: int, user: User = Depends(get_current_user)):
    """Get account equity, P&L, and open positions."""
    try:
        return AccountSummaryResponse(**paper_trading_engine.get_account_summary(account_id))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/accounts/{account_id}/orders", response_model=OrderResponse)
def submit_order(
    account_id: int,
    request: OrderRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit a paper order. Fills immediately against the supplied or latest price."""
    if paper_trading_engine.get_account(account_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown account: {account_id}")

    market_price = request.market_price
    volume = request.volume
    if market_price is None:
        latest = _latest_price(db, request.symbol)
        if latest is None:
            raise HTTPException(
                status_code=400,
                detail=(f"No price history for {request.symbol}; supply market_price explicitly."),
            )
        price_dec, volume = latest
        market_price = float(price_dec)

    try:
        order = paper_trading_engine.execute_order(
            account_id=account_id,
            symbol=request.symbol,
            side=request.side.upper(),
            quantity=Decimal(str(request.quantity)),
            market_price=Decimal(str(market_price)),
            order_type=request.order_type.upper(),
            limit_price=Decimal(str(request.limit_price))
            if request.limit_price is not None
            else None,
            volume=volume,
        )
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return _order_to_response(order)


@router.get("/accounts/{account_id}/trades", response_model=list[OrderResponse])
def get_trades(
    account_id: int,
    user: User = Depends(get_current_user),
    limit: int = Query(default=100, ge=1, le=1000),
):
    """Get order/trade history for an account, most recent first."""
    try:
        orders = paper_trading_engine.get_trades(account_id, limit=limit)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return [_order_to_response(o) for o in orders]


@router.get("/health")
def paper_trading_health():
    """Health check for the paper trading service."""
    return {
        "status": "healthy",
        "service": "paper-trading",
        "accounts": len(paper_trading_engine.list_accounts()),
    }
