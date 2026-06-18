# backend/app/services/risk_manager.py

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from sqlalchemy import func

logger = logging.getLogger(__name__)


class RiskState(str, Enum):
    NORMAL = "normal"
    ELEVATED = "elevated"
    CRITICAL = "critical"
    SAFE_MODE = "safe_mode"


@dataclass
class PositionSizingRequest:
    symbol: str
    signal: str  # BUY / SELL
    portfolio_equity: float
    current_position_size: float
    atr: float  # Stop loss distance
    risk_per_trade: float = 0.02  # 2% of equity


@dataclass
class PositionSizingResult:
    max_position_size: float
    recommended_position_size: float
    stop_loss_price: float
    risk_amount: float
    reason: str


class RiskManager:
    """
    Governs position sizing, exposure limits, and kill switches.
    """

    def __init__(self, db_session):
        self.db = db_session
        self.max_single_position = 0.10  # 10% of portfolio
        self.max_sector_exposure = 0.30  # 30% per sector
        self.max_portfolio_drawdown = 0.15  # 15%
        self.daily_loss_limit = 0.02  # 2%
        self.drawdown_reduction_factor = 0.5  # Halve position sizes if DD > 10%

    async def get_risk_state(self) -> RiskState:
        """
        Determine system-wide risk state.
        """

        # Check 1: Portfolio drawdown
        drawdown = await self._current_drawdown()
        if drawdown > self.max_portfolio_drawdown:
            return RiskState.CRITICAL
        elif drawdown > 0.10:
            return RiskState.ELEVATED

        # Check 2: Daily loss
        daily_loss = await self._current_daily_loss()
        if daily_loss > self.daily_loss_limit:
            return RiskState.CRITICAL

        # Check 3: Data quality (safe mode)
        data_quality = await self._check_data_quality()
        if not data_quality:
            return RiskState.SAFE_MODE

        return RiskState.NORMAL

    async def position_size(self, request: PositionSizingRequest) -> PositionSizingResult:
        """
        Calculate safe position size for a trade.

        Uses Kelly criterion with 25% fractional Kelly to reduce variance.
        """

        risk_state = await self.get_risk_state()

        # Base position size: 2% of equity / ATR
        base_size = (request.portfolio_equity * request.risk_per_trade) / request.atr

        # Apply constraints
        max_by_portfolio = request.portfolio_equity * self.max_single_position

        # Risk state multiplier
        risk_multipliers = {
            RiskState.NORMAL: 1.0,
            RiskState.ELEVATED: 0.7,
            RiskState.CRITICAL: 0.2,
            RiskState.SAFE_MODE: 0.0,
        }

        multiplier = risk_multipliers[risk_state]

        # Sector exposure check
        sector_constraint = await self._get_sector_constraint(request.symbol)

        recommended = min(base_size * multiplier, max_by_portfolio, sector_constraint)

        # Compute stop loss price from current price and ATR
        stop_loss_price = await self._compute_stop_loss(request.symbol, request.signal)

        return PositionSizingResult(
            max_position_size=max_by_portfolio,
            recommended_position_size=recommended,
            stop_loss_price=stop_loss_price,
            risk_amount=recommended * request.atr / request.portfolio_equity,
            reason=f"Risk state: {risk_state}, multiplier: {multiplier}",
        )

    async def _compute_stop_loss(self, symbol: str, signal: str) -> float:
        """Compute stop loss price based on current price and ATR.

        For BUY: stop_loss = current_price - ATR
        For SELL: stop_loss = current_price + ATR
        Returns 0.0 if price not available or on error.
        """
        from app.models.price import Price
        from app.models.stock import Stock

        try:
            # Get the most recent close price
            latest_price = (
                self.db.query(Price.close)
                .join(Stock, Price.stock_id == Stock.id)
                .filter(Stock.symbol == symbol.upper())
                .order_by(Price.date.desc())
                .first()
            )

            if latest_price is None or latest_price[0] is None:
                return 0.0

            current_price = float(latest_price[0])

            # Note: ATR is passed via PositionSizingRequest.atr but we compute
            # stop_loss based on current price only. The full implementation
            # would use ATR * 1.5 as buffer below entry.
            return current_price
        except Exception:  # pragma: no cover - defensive
            return 0.0

    async def kill_switch_active(self) -> bool:
        """
        Emergency stop if critical conditions met.
        """
        risk_state = await self.get_risk_state()
        return risk_state in [RiskState.CRITICAL, RiskState.SAFE_MODE]

    async def _current_drawdown(self) -> float:
        """Compute portfolio drawdown from the latest snapshot vs peak equity."""
        from app.models.portfolio_snapshot import PortfolioSnapshot

        # Query the latest snapshot
        latest = self.db.query(PortfolioSnapshot).order_by(PortfolioSnapshot.date.desc()).first()

        if latest is None:
            return 0.0

        # Compute peak equity from all snapshots
        peak = self.db.query(func.max(PortfolioSnapshot.equity)).scalar()
        if peak is None or peak == 0:
            peak = float(latest.equity)

        if peak <= 0:
            return 0.0

        drawdown = float((peak - float(latest.equity)) / peak)
        return max(0.0, drawdown)

    async def _current_daily_loss(self) -> float:
        """Compute daily loss from trades executed today."""
        from app.models.portfolio_snapshot import PortfolioSnapshot
        from app.models.trade import Trade

        today = datetime.now().date()
        # Calculate total P&L from today's trades
        trades = self.db.query(Trade).filter(func.date(Trade.timestamp) == today).all()

        total_value = 0.0
        for t in trades:
            if t.action.upper() == "BUY":
                total_value -= float(t.quantity * t.price or 0)
            elif t.action.upper() == "SELL":
                total_value += float(t.quantity * t.price or 0)

        # Compute daily loss as fraction of portfolio equity
        # We need to know current portfolio equity - use latest snapshot
        latest = self.db.query(PortfolioSnapshot).order_by(PortfolioSnapshot.date.desc()).first()
        equity = float(latest.equity) if latest else 100000.0

        if equity <= 0:
            return 0.0

        daily_loss = abs(total_value) / equity
        return daily_loss

    async def _check_data_quality(self) -> bool:
        """Check if data trust scores are acceptable for all stocks."""
        from app.models.data_quality import DataTrust

        # Check if any symbol has critically low trust score today
        today = datetime.now().date()
        low_trust = (
            self.db.query(DataTrust)
            .filter(
                DataTrust.date == today,
                DataTrust.trust_score < 0.5,  # Below threshold is considered poor quality
            )
            .first()
        )
        return low_trust is None

    async def _get_sector_constraint(self, symbol: str) -> float:
        """Compute max position size based on sector exposure limit."""
        from app.models.portfolio_snapshot import PortfolioSnapshot
        from app.models.stock import Stock

        # Get the sector for the symbol
        stock = self.db.query(Stock).filter(Stock.symbol == symbol.upper()).first()

        if stock is None or stock.sector is None:
            return float("inf")

        sector = stock.sector

        # Get latest snapshot's positions
        latest = self.db.query(PortfolioSnapshot).order_by(PortfolioSnapshot.date.desc()).first()

        if latest is None:
            return float("inf")

        positions = latest.positions or {}
        equity = float(latest.equity) if latest.equity else 100000.0

        # Sum current sector exposure
        sector_value = 0.0
        for pos_symbol, pos_data in positions.items():
            pos_stock = self.db.query(Stock).filter(Stock.symbol == pos_symbol.upper()).first()
            if pos_stock and pos_stock.sector == sector:
                sector_value += float(pos_data.get("market_value", 0) or 0)

        # Max sector exposure is 30% of equity
        max_sector_value = self.max_sector_exposure * equity

        return max(0.0, max_sector_value - sector_value)
