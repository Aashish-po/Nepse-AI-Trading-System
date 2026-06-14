"""Signal heatmap and backfill API routes."""

import datetime as dt
from datetime import datetime
from typing import Annotated

import sqlalchemy as sa
from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.signal import Signal
from app.models.stock import Stock
from app.schemas.signals import ProviderQuotaResponse, ProviderQuotaSummaryResponse
from app.services.data_quality_gate import DataQualityGateError
from app.services.provider_quota import ProviderQuotaService
from app.services.risk_manager import PositionSizingRequest, RiskManager
from app.services.signal_backfill import SignalBackfillService
from app.services.signal_fusion import SignalFusionEngine
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

router = APIRouter(prefix="/signals", tags=["signals"])
DbSession = Annotated[Session, Depends(get_db)]


@router.get("/heatmap/{date_str}")
def get_signal_heatmap(date_str: str, db: DbSession) -> dict:
    """Get signal distribution heatmap for a date."""
    try:
        parsed_date = dt.date.fromisoformat(date_str)
    except ValueError:
        return {"error": "Invalid date format. Use YYYY-MM-DD."}

    rows = db.execute(
        sa.select(
            Stock.symbol,
            Signal.signal_type,
            Signal.value,
            Signal.confidence,
        )
        .join(Stock, Signal.stock_id == Stock.id)
        .where(Signal.date == parsed_date)
    ).all()

    if not rows:
        return {"date": date_str, "heat_data": [], "message": "No signals for this date"}

    return {
        "date": date_str,
        "heat_data": [
            {
                "symbol": row.symbol,
                "signal_type": row.signal_type,
                "value": float(row.value) if row.value else 0.0,
                "confidence": float(row.confidence) if row.confidence else None,
            }
            for row in rows
        ],
    }


@router.get("/quota", response_model=ProviderQuotaSummaryResponse)
def list_provider_quotas(
    db: DbSession,
    date: str | None = Query(default=None),
) -> ProviderQuotaSummaryResponse:
    service = ProviderQuotaService(session=db)
    providers_raw = service.list_statuses(quota_date=date)
    providers = [ProviderQuotaResponse(**item) for item in providers_raw]

    summary_date = providers[0].date if providers else (date or dt.date.today().isoformat())

    return ProviderQuotaSummaryResponse(
        date=summary_date,
        providers=providers,
        total_request_count=sum(p.request_count for p in providers),
        total_signal_count=sum(p.signal_count for p in providers),
        total_success_count=sum(p.success_count for p in providers),
        total_failure_count=sum(p.failure_count for p in providers),
        total_skipped_count=sum(p.skipped_count for p in providers),
        total_token_count=sum(p.token_count for p in providers),
        total_cost=sum(p.cost for p in providers),
    )


@router.get("/quota/{provider}", response_model=ProviderQuotaResponse)
def get_provider_quota(
    provider: str,
    db: DbSession,
    date: str | None = Query(default=None),
) -> ProviderQuotaResponse:
    service = ProviderQuotaService(session=db)
    return ProviderQuotaResponse(**service.get_status(provider, quota_date=date))


@router.post("/backfill-all")
def backfill_all_signals(
    start_date: str,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    upsert: bool = True,
    symbols: list[str] | None = Query(default=None),
) -> dict:
    """Backfill rule-based signals for active symbols or an explicit symbol list."""
    try:
        backfill = SignalBackfillService(session=db)
        return backfill.backfill_all(
            start_date=start_date,
            end_date=end_date,
            symbols=symbols,
            upsert=upsert,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/backfill/{symbol}")
def backfill_signals(
    symbol: str,
    start_date: str,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    upsert: bool = True,
) -> dict:
    """Backfill rule-based signals for a symbol."""
    session = db
    try:
        backfill = SignalBackfillService(session=session)
        return backfill.backfill_symbol(
            symbol,
            start_date=start_date,
            end_date=end_date,
            upsert=upsert,
        )
    except DataQualityGateError as exc:
        return {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.post("/fuse")
async def fuse_signal(
    symbol: str = Query(..., min_length=1, max_length=20),
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Fuse technical + ML + sentiment signals into actionable advisory.

    Response:
    {
      "symbol": "NABIL",
      "signal": "BUY",
      "confidence": 0.82,
      "explanation": {...},
      "risk_assessment": {...},
      "raw_scores": {"technical": 0.8, "ml": 0.85, "sentiment": 0.75},
      "weights_used": {"technical": 0.3, "ml": 0.4, "sentiment": 0.3},
      "is_actionable": true
    }
    """

    fusion_engine = SignalFusionEngine(db)

    # Fetch latest signals from each provider
    technical = await db.query(
        "SELECT * FROM signals WHERE provider='technical' AND symbol=?", [symbol]
    )
    ml = await db.query("SELECT * FROM signals WHERE provider='ml' AND symbol=?", [symbol])
    sentiment = await db.query(
        "SELECT * FROM signals WHERE provider='sentiment' AND symbol=?", [symbol]
    )

    # Infer regime (TODO: implement)
    regime = "bull"  # placeholder

    # Get risk state
    risk_mgr = RiskManager(db)
    risk_state = await risk_mgr.get_risk_state()

    # Fuse
    fused = await fusion_engine.fuse(
        symbol=symbol,
        date=datetime.utcnow(),
        technical_signal=technical.dict() if technical else None,
        ml_signal=ml.dict() if ml else None,
        sentiment_signal=sentiment.dict() if sentiment else None,
        regime=regime,
        risk_state=str(risk_state),
    )

    return {
        "symbol": fused.symbol,
        "signal": fused.signal.value,
        "confidence": fused.confidence,
        "explanation": fused.explanation,
        "risk_assessment": fused.risk_assessment,
        "raw_scores": fused.raw_scores,
        "weights_used": fused.weights_used,
        "is_actionable": fused.is_actionable(),
        "timestamp": fused.date.isoformat(),
    }


@router.get("/risk-state")
async def get_risk_state(user: dict = Depends(get_current_user), db=Depends(get_db)):
    """Get current system risk state."""
    risk_mgr = RiskManager(db)
    state = await risk_mgr.get_risk_state()
    kill_switch = await risk_mgr.kill_switch_active()

    return {
        "risk_state": state.value,
        "kill_switch_active": kill_switch,
        "advisory_status": "HOLD_ONLY" if kill_switch else "NORMAL",
    }


@router.post("/position-size")
async def calculate_position_size(
    symbol: str,
    signal: str,
    portfolio_equity: float,
    atr: float,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Calculate max safe position size given current risk state."""

    risk_mgr = RiskManager(db)

    result = await risk_mgr.position_size(
        PositionSizingRequest(
            symbol=symbol,
            signal=signal,
            portfolio_equity=portfolio_equity,
            current_position_size=0.0,  # TODO: query from portfolio_snapshots
            atr=atr,
        )
    )

    return {
        "max_position_size": result.max_position_size,
        "recommended_position_size": result.recommended_position_size,
        "stop_loss_price": result.stop_loss_price,
        "risk_amount": result.risk_amount,
        "reason": result.reason,
    }
