import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import cast

logger = logging.getLogger(__name__)


@dataclass
class Transaction:
    """Represents a single buy/sell transaction."""

    symbol: str
    action: str  # BUY or SELL
    quantity: Decimal
    price: Decimal
    timestamp: datetime
    fees: Decimal = Decimal("0.00")


@dataclass
class Position:
    """Represents a current position in a stock."""

    symbol: str
    quantity: Decimal
    average_price: Decimal
    current_price: Decimal | None = None

    @property
    def market_value(self) -> Decimal:
        if self.current_price is None:
            return self.quantity * self.average_price
        return self.quantity * self.current_price

    @property
    def unrealized_pnl(self) -> Decimal:
        if self.current_price is None:
            return Decimal("0.00")

        left = cast(Decimal, self.current_price * self.quantity)
        right = cast(Decimal, self.average_price * self.quantity)
        return left - right  # type: ignore[return-value]


@dataclass
class PortfolioSnapshot:
    """Snapshot of portfolio state at a point in time."""

    id: int | None = field(default=None)
    date: datetime = field(default_factory=datetime.now)
    equity: Decimal = field(default=Decimal("0.00"))
    cash: Decimal = field(default=Decimal("0.00"))
    positions: dict[str, Position] = field(default_factory=dict)

    @property
    def total_market_value(self) -> Decimal:
        return sum((pos.market_value for pos in self.positions.values()), start=Decimal("0.00"))

    @property
    def total_unrealized_pnl(self) -> Decimal:
        return sum((pos.unrealized_pnl for pos in self.positions.values()), start=Decimal("0.00"))


class PortfolioAccountService:
    """Service for managing portfolio accounts, simulating trades, and tracking performance."""

    def __init__(self, initial_capital: Decimal = Decimal("100000.00")):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: dict[str, Position] = {}
        self.transactions: list[Transaction] = []
        logger.info(f"PortfolioAccountService initialized with capital: {initial_capital}")

    def deposit(self, amount: Decimal) -> None:
        """Deposit cash into the portfolio account."""
        if amount <= 0:
            raise ValueError("Deposit amount must be positive")
        self.cash += amount
        self._record_transaction("DEPOSIT", amount)
        logger.info(f"Deposited {amount}. New cash balance: {self.cash}")

    def withdraw(self, amount: Decimal) -> None:
        """Withdraw cash from the portfolio account."""
        if amount <= 0:
            raise ValueError("Withdrawal amount must be positive")
        if amount > self.cash:
            raise ValueError("Insufficient funds for withdrawal")
        self.cash -= amount
        self._record_transaction("WITHDRAWAL", amount)
        logger.info(f"Withdrew {amount}. New cash balance: {self.cash}")

    def buy(
        self, symbol: str, quantity: Decimal, price: Decimal, fees: Decimal = Decimal("0.00")
    ) -> bool:
        """Buy a stock position."""
        total_cost = quantity * price + fees
        if total_cost > self.cash:
            logger.warning(f"Insufficient funds to buy {quantity} {symbol} at {price}")
            return False

        # Update or create position
        if symbol in self.positions:
            pos = self.positions[symbol]
            # Calculate new average price
            total_quantity = pos.quantity + quantity
            total_cost_basis = (pos.quantity * pos.average_price) + (quantity * price)
            pos.average_price = total_cost_basis / total_quantity
            pos.quantity = total_quantity
        else:
            self.positions[symbol] = Position(symbol=symbol, quantity=quantity, average_price=price)

        # Update cash and record transaction
        self.cash -= total_cost
        self.transactions.append(
            Transaction(
                symbol=symbol,
                action="BUY",
                quantity=quantity,
                price=price,
                timestamp=datetime.now(),
                fees=fees,
            )
        )

        logger.info(f"Bought {quantity} {symbol} at {price}. Cash remaining: {self.cash}")
        return True

    def sell(
        self, symbol: str, quantity: Decimal, price: Decimal, fees: Decimal = Decimal("0.00")
    ) -> bool:
        """Sell a stock position."""
        if symbol not in self.positions:
            logger.warning(f"No position found for {symbol}")
            return False

        pos = self.positions[symbol]
        if pos.quantity < quantity:
            logger.warning(
                f"Insufficient shares to sell. Have {pos.quantity}, trying to sell {quantity}"
            )
            return False

        # Update position
        pos.quantity -= quantity
        if pos.quantity == 0:
            del self.positions[symbol]

        # Update cash and record transaction
        proceeds = quantity * price - fees
        self.cash += proceeds
        self.transactions.append(
            Transaction(
                symbol=symbol,
                action="SELL",
                quantity=quantity,
                price=price,
                timestamp=datetime.now(),
                fees=fees,
            )
        )

        logger.info(f"Sold {quantity} {symbol} at {price}. Cash remaining: {self.cash}")
        return True

    def update_position_price(self, symbol: str, price: Decimal) -> None:
        """Update the current market price for a position."""
        if symbol in self.positions:
            self.positions[symbol].current_price = price

    def get_portfolio_snapshot(self) -> PortfolioSnapshot:
        """Get current portfolio snapshot."""
        # Update positions with current prices if available
        for position in self.positions.values():
            if position.current_price is None:
                position.current_price = position.average_price

        return PortfolioSnapshot(
            date=datetime.now(),
            equity=self.get_total_equity(),
            cash=self.cash,
            positions=self.positions.copy(),
        )

    def get_total_equity(self) -> Decimal:
        """Get total portfolio equity (cash + positions value)."""
        positions_value = Decimal("0.00")
        for position in self.positions.values():
            if position.current_price is not None:
                positions_value += position.quantity * position.current_price
            else:
                positions_value += position.quantity * position.average_price
        return self.cash + positions_value

    def get_allocation(self) -> dict[str, float]:
        """Get current portfolio allocation as percentages."""
        total_equity = self.get_total_equity()
        if total_equity == 0:
            return {}

        allocation: dict[str, float] = {}
        # Cash allocation
        allocation["CASH"] = float(self.cash / total_equity * 100)

        # Position allocations
        for symbol, position in self.positions.items():
            position_value = position.market_value
            allocation[symbol] = float(position_value / total_equity * 100)

        return allocation

    def get_transaction_history(self) -> list[Transaction]:
        """Get list of all transactions."""
        return self.transactions.copy()

    def get_weights(self) -> dict[str, float]:
        """Current portfolio weights by symbol as a fraction of total equity.

        Cash is excluded; weights sum to (1 - cash_fraction).
        """
        total_equity = self.get_total_equity()
        if total_equity == 0:
            return {}
        return {
            symbol: float(position.market_value / total_equity)
            for symbol, position in self.positions.items()
        }

    def compute_drift(self, target_weights: dict[str, float]) -> dict[str, float]:
        """Absolute drift of each symbol's current weight from its target.

        Symbols present in either the current portfolio or the target are
        considered, so a position that should be fully exited (target 0) still
        registers its drift.
        """
        current = self.get_weights()
        symbols = set(current) | set(target_weights)
        return {
            symbol: abs(current.get(symbol, 0.0) - float(target_weights.get(symbol, 0.0)))
            for symbol in symbols
        }

    def should_rebalance(self, target_weights: dict[str, float], threshold: float = 0.05) -> bool:
        """True if any symbol has drifted from its target by more than ``threshold``.

        Default threshold is 5%, matching the rebalance policy in the enhancement plan.
        """
        drift = self.compute_drift(target_weights)
        if not drift:
            return False
        return max(drift.values()) > threshold

    def _record_transaction(self, action: str, amount: Decimal) -> None:
        """Record a non-trade transaction (deposit/withdrawal)."""
        self.transactions.append(
            Transaction(
                symbol="CASH",
                action=action,
                quantity=amount,
                price=Decimal("1.00"),
                timestamp=datetime.now(),
            )
        )
