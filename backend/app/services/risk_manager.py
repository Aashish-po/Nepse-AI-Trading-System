# backend/app/services/risk_manager.py

import logging
from dataclasses import dataclass
from enum import Enum

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

        return PositionSizingResult(
            max_position_size=max_by_portfolio,
            recommended_position_size=recommended,
            stop_loss_price=0.0,  # TODO: compute from ATR
            risk_amount=recommended * request.atr / request.portfolio_equity,
            reason=f"Risk state: {risk_state}, multiplier: {multiplier}",
        )

    async def kill_switch_active(self) -> bool:
        """
        Emergency stop if critical conditions met.
        """
        risk_state = await self.get_risk_state()
        return risk_state in [RiskState.CRITICAL, RiskState.SAFE_MODE]

    # ------------------------------------------------------------------
    # NOT IMPLEMENTED: the checks below have no live portfolio/holdings data
    # source yet, so they return permissive defaults (drawdown=0, checks pass).
    # This means risk enforcement is ADVISORY ONLY. API responses expose
    # ``enforced: False`` so callers never treat these as real risk controls.
    # Do not rely on get_risk_state()/kill_switch_active() to block live trades.
    # ------------------------------------------------------------------

    async def _current_drawdown(self) -> float:
        """NOT IMPLEMENTED: no portfolio snapshot source. Returns 0.0 (no drawdown)."""
        return 0.0

    async def _current_daily_loss(self) -> float:
        """NOT IMPLEMENTED: no transaction-log source. Returns 0.0 (no loss)."""
        return 0.0

    async def _check_data_quality(self) -> bool:
        """NOT IMPLEMENTED: no trust-score wiring here. Returns True (passes)."""
        return True

    async def _get_sector_constraint(self, symbol: str) -> float:
        """NOT IMPLEMENTED: no sector holdings source. Returns inf (no constraint)."""
        return float("inf")
