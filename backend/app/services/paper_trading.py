"""Paper trading engine.

Simulates live order execution against real market prices without touching real
capital. It is the bridge between historical backtesting (``backtest.py``) and
live trading: orders are filled with the same realistic slippage / commission /
partial-fill model used by :class:`~app.services.backtest.BacktestEngine`, but
the account state is held in memory and marked-to-market on demand.

Design goals:
- Reuse the backtest execution assumptions (commission, slippage bps, liquidity
  cap) so paper results are comparable to backtests.
- Decimal arithmetic throughout, matching ``PortfolioAccountService``.
- Deterministic, dependency-free core so it is trivially unit-testable: market
  prices and volumes are passed in, never fetched here. The API layer is
  responsible for sourcing live prices.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

logger = logging.getLogger(__name__)

# Execution assumptions, kept in sync with BacktestEngine defaults so paper
# trading and backtests fill orders under the same model.
DEFAULT_COMMISSION_RATE = Decimal("0.005")  # 0.5% of notional
DEFAULT_SLIPPAGE_BPS = Decimal("5.0")  # 5 basis points adverse price move
DEFAULT_PARTIAL_FILL_THRESHOLD = Decimal("0.3")  # max share of bar volume per order


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus(StrEnum):
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    PENDING = "PENDING"  # limit order not marketable at current price


@dataclass
class PaperPosition:
    """A simulated open position."""

    symbol: str
    quantity: Decimal
    average_price: Decimal
    current_price: Decimal | None = None

    @property
    def market_value(self) -> Decimal:
        price = self.current_price if self.current_price is not None else self.average_price
        return self.quantity * price

    @property
    def cost_basis(self) -> Decimal:
        return self.quantity * self.average_price

    @property
    def unrealized_pnl(self) -> Decimal:
        if self.current_price is None:
            return Decimal("0.00")
        return (self.current_price - self.average_price) * self.quantity


@dataclass
class PaperOrder:
    """Record of a submitted order and its simulated execution outcome."""

    id: int
    account_id: int
    symbol: str
    side: OrderSide
    order_type: OrderType
    requested_quantity: Decimal
    timestamp: datetime
    status: OrderStatus = OrderStatus.PENDING
    limit_price: Decimal | None = None
    filled_quantity: Decimal = Decimal("0")
    fill_price: Decimal | None = None
    commission: Decimal = Decimal("0.00")
    slippage_cost: Decimal = Decimal("0.00")
    realized_pnl: Decimal = Decimal("0.00")
    message: str = ""


@dataclass
class PaperTradingAccount:
    """In-memory simulated trading account."""

    id: int
    name: str
    initial_capital: Decimal
    cash: Decimal
    created_at: datetime
    positions: dict[str, PaperPosition] = field(default_factory=dict)
    orders: list[PaperOrder] = field(default_factory=list)
    realized_pnl: Decimal = Decimal("0.00")
    equity_curve: list[dict] = field(default_factory=list)

    def positions_value(self) -> Decimal:
        return sum((p.market_value for p in self.positions.values()), start=Decimal("0.00"))

    def equity(self) -> Decimal:
        return self.cash + self.positions_value()


class PaperTradingEngine:
    """Manages paper trading accounts and simulates order execution.

    Market prices and (optional) bar volumes are supplied by the caller; this
    keeps the engine deterministic and free of data-layer dependencies.
    """

    def __init__(
        self,
        commission_rate: Decimal = DEFAULT_COMMISSION_RATE,
        slippage_bps: Decimal = DEFAULT_SLIPPAGE_BPS,
        partial_fill_threshold: Decimal = DEFAULT_PARTIAL_FILL_THRESHOLD,
    ) -> None:
        self.commission_rate = commission_rate
        self.slippage_bps = slippage_bps
        self.partial_fill_threshold = partial_fill_threshold
        self._accounts: dict[int, PaperTradingAccount] = {}
        self._next_account_id = 1
        self._next_order_id = 1

    # ------------------------------------------------------------------ accounts
    def create_account(
        self, name: str, initial_capital: Decimal = Decimal("1000000.00")
    ) -> PaperTradingAccount:
        if initial_capital <= 0:
            raise ValueError("initial_capital must be positive")
        account = PaperTradingAccount(
            id=self._next_account_id,
            name=name,
            initial_capital=initial_capital,
            cash=initial_capital,
            created_at=datetime.now(),
        )
        self._accounts[account.id] = account
        self._next_account_id += 1
        logger.info(
            "Created paper trading account %s (%s) with %s", account.id, name, initial_capital
        )
        return account

    def get_account(self, account_id: int) -> PaperTradingAccount | None:
        return self._accounts.get(account_id)

    def list_accounts(self) -> list[PaperTradingAccount]:
        return list(self._accounts.values())

    # ----------------------------------------------------------------- execution
    def _apply_slippage(self, price: Decimal, side: OrderSide) -> Decimal:
        """Move the fill price adversely by ``slippage_bps`` (buys up, sells down)."""
        factor = self.slippage_bps / Decimal("10000")
        if side == OrderSide.BUY:
            return price * (1 + factor)
        return price * (1 - factor)

    def _fill_quantity(self, desired: Decimal, volume: int | None) -> Decimal:
        """Cap fill size by available liquidity.

        Mirrors ``BacktestEngine._calculate_fill_rate``: an order up to 30% of bar
        volume fills completely; larger orders are partially filled and capped at
        70% of the requested size.
        """
        if volume is None:
            return desired
        vol = Decimal(str(volume))
        if desired <= vol * self.partial_fill_threshold:
            return desired
        fill_rate = min(Decimal("0.7"), (vol * self.partial_fill_threshold) / desired)
        # Floor to whole shares.
        return Decimal(int(desired * fill_rate))

    def execute_order(
        self,
        account_id: int,
        symbol: str,
        side: OrderSide | str,
        quantity: Decimal | int,
        market_price: Decimal,
        order_type: OrderType | str = OrderType.MARKET,
        limit_price: Decimal | None = None,
        volume: int | None = None,
    ) -> PaperOrder:
        """Simulate execution of a single order and update account state."""
        account = self._accounts.get(account_id)
        if account is None:
            raise KeyError(f"Unknown paper trading account: {account_id}")

        side = OrderSide(side)
        order_type = OrderType(order_type)
        symbol = symbol.upper()
        quantity = Decimal(str(quantity))
        market_price = Decimal(str(market_price))
        if limit_price is not None:
            limit_price = Decimal(str(limit_price))

        order = PaperOrder(
            id=self._next_order_id,
            account_id=account_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            requested_quantity=quantity,
            limit_price=limit_price,
            timestamp=datetime.now(),
        )
        self._next_order_id += 1
        account.orders.append(order)

        if quantity <= 0:
            order.status = OrderStatus.REJECTED
            order.message = "Quantity must be positive"
            return order
        if order_type == OrderType.LIMIT and limit_price is None:
            order.status = OrderStatus.REJECTED
            order.message = "Limit order requires a limit_price"
            return order

        # Determine the marketable execution price.
        exec_price = self._apply_slippage(market_price, side)
        if order_type == OrderType.LIMIT:
            assert limit_price is not None
            if side == OrderSide.BUY:
                if market_price > limit_price:
                    order.status = OrderStatus.PENDING
                    order.message = f"Buy limit {limit_price} below market {market_price}"
                    return order
                # Never pay more than the limit.
                exec_price = min(exec_price, limit_price)
            else:  # SELL
                if market_price < limit_price:
                    order.status = OrderStatus.PENDING
                    order.message = f"Sell limit {limit_price} above market {market_price}"
                    return order
                # Never sell below the limit.
                exec_price = max(exec_price, limit_price)

        if side == OrderSide.BUY:
            self._execute_buy(account, order, exec_price, market_price, volume)
        else:
            self._execute_sell(account, order, exec_price, market_price, volume)
        return order

    def _execute_buy(
        self,
        account: PaperTradingAccount,
        order: PaperOrder,
        exec_price: Decimal,
        market_price: Decimal,
        volume: int | None,
    ) -> None:
        fill_qty = self._fill_quantity(order.requested_quantity, volume)

        # Constrain by available cash (price + commission per share).
        per_share_cost = exec_price * (1 + self.commission_rate)
        if per_share_cost > 0:
            affordable = Decimal(int(account.cash / per_share_cost))
            fill_qty = min(fill_qty, affordable)

        if fill_qty <= 0:
            order.status = OrderStatus.REJECTED
            order.message = "Insufficient cash to fill any shares"
            return

        notional = fill_qty * exec_price
        commission = notional * self.commission_rate
        total_cost = notional + commission

        account.cash -= total_cost
        pos = account.positions.get(order.symbol)
        if pos is None:
            account.positions[order.symbol] = PaperPosition(
                symbol=order.symbol,
                quantity=fill_qty,
                average_price=exec_price,
                current_price=market_price,
            )
        else:
            new_qty = pos.quantity + fill_qty
            pos.average_price = (pos.cost_basis + notional) / new_qty
            pos.quantity = new_qty
            pos.current_price = market_price

        self._finalize(order, fill_qty, exec_price, market_price, commission)

    def _execute_sell(
        self,
        account: PaperTradingAccount,
        order: PaperOrder,
        exec_price: Decimal,
        market_price: Decimal,
        volume: int | None,
    ) -> None:
        pos = account.positions.get(order.symbol)
        if pos is None or pos.quantity <= 0:
            order.status = OrderStatus.REJECTED
            order.message = f"No open position in {order.symbol}"
            return

        fill_qty = self._fill_quantity(order.requested_quantity, volume)
        fill_qty = min(fill_qty, pos.quantity)
        if fill_qty <= 0:
            order.status = OrderStatus.REJECTED
            order.message = "No shares available to sell"
            return

        notional = fill_qty * exec_price
        commission = notional * self.commission_rate
        proceeds = notional - commission

        realized = (exec_price - pos.average_price) * fill_qty - commission
        account.cash += proceeds
        account.realized_pnl += realized
        order.realized_pnl = realized

        pos.quantity -= fill_qty
        pos.current_price = market_price
        if pos.quantity <= 0:
            del account.positions[order.symbol]

        self._finalize(order, fill_qty, exec_price, market_price, commission)

    def _finalize(
        self,
        order: PaperOrder,
        fill_qty: Decimal,
        exec_price: Decimal,
        market_price: Decimal,
        commission: Decimal,
    ) -> None:
        order.filled_quantity = fill_qty
        order.fill_price = exec_price
        order.commission = commission
        # Slippage cost = adverse price move applied over the filled quantity.
        order.slippage_cost = abs(exec_price - market_price) * fill_qty
        order.status = (
            OrderStatus.FILLED if fill_qty >= order.requested_quantity else OrderStatus.PARTIAL
        )
        order.message = "Order filled" if order.status == OrderStatus.FILLED else "Partially filled"

    # ----------------------------------------------------------- mark-to-market
    def mark_to_market(
        self, account_id: int, prices: dict[str, Decimal], timestamp: datetime | None = None
    ) -> Decimal:
        """Update positions with current prices and append an equity-curve point."""
        account = self._accounts.get(account_id)
        if account is None:
            raise KeyError(f"Unknown paper trading account: {account_id}")
        for symbol, position in account.positions.items():
            if symbol in prices:
                position.current_price = Decimal(str(prices[symbol]))
        equity = account.equity()
        account.equity_curve.append(
            {
                "timestamp": (timestamp or datetime.now()).isoformat(),
                "equity": float(equity),
                "cash": float(account.cash),
                "positions_value": float(account.positions_value()),
            }
        )
        return equity

    # ------------------------------------------------------------------ summary
    def get_account_summary(self, account_id: int) -> dict:
        account = self._accounts.get(account_id)
        if account is None:
            raise KeyError(f"Unknown paper trading account: {account_id}")

        positions_value = account.positions_value()
        equity = account.cash + positions_value
        unrealized = sum(
            (p.unrealized_pnl for p in account.positions.values()), start=Decimal("0.00")
        )
        total_pnl = equity - account.initial_capital
        total_return_pct = (
            float(total_pnl / account.initial_capital * 100) if account.initial_capital else 0.0
        )

        return {
            "account_id": account.id,
            "name": account.name,
            "created_at": account.created_at.isoformat(),
            "initial_capital": float(account.initial_capital),
            "cash": float(account.cash),
            "positions_value": float(positions_value),
            "equity": float(equity),
            "realized_pnl": float(account.realized_pnl),
            "unrealized_pnl": float(unrealized),
            "total_pnl": float(total_pnl),
            "total_return_pct": total_return_pct,
            "open_positions": len(account.positions),
            "order_count": len(account.orders),
            "equity_curve": list(account.equity_curve),
            "positions": {
                symbol: {
                    "symbol": p.symbol,
                    "quantity": float(p.quantity),
                    "average_price": float(p.average_price),
                    "current_price": float(p.current_price)
                    if p.current_price is not None
                    else None,
                    "market_value": float(p.market_value),
                    "unrealized_pnl": float(p.unrealized_pnl),
                }
                for symbol, p in account.positions.items()
            },
        }

    def get_trades(self, account_id: int, limit: int = 100) -> list[PaperOrder]:
        account = self._accounts.get(account_id)
        if account is None:
            raise KeyError(f"Unknown paper trading account: {account_id}")
        # Most recent first.
        return list(reversed(account.orders))[:limit]


# Module-level singleton, mirroring the in-memory account store used by the
# portfolio route. Replace with a DB-backed store for multi-process deployments.
paper_trading_engine = PaperTradingEngine()
