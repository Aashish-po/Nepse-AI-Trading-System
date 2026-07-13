"""Signal heatmap and backfill API routes."""

import datetime as dt
import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated

import numpy as np
import sqlalchemy as sa
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.signal import Signal
from app.models.stock import Stock
from app.models.user import User
from app.schemas.signals import ProviderQuotaResponse, ProviderQuotaSummaryResponse
from app.services.data_quality_gate import DataQualityGateError
from app.services.feature import FeatureService
from app.services.provider_quota import ProviderQuotaService
from app.services.risk_manager import PositionSizingRequest, RiskManager
from app.services.signal_backfill import SignalBackfillService
from app.services.signal_fusion import SignalFusionEngine
from app.services.signal_streamer import signal_stream_publisher
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/signals", tags=["signals"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def _latest_signal(db: Session, symbol: str, provider: str) -> Signal | None:
    """Fetch the most recent signal for a symbol from one provider (parameterized ORM)."""
    return db.scalar(
        sa.select(Signal)
        .join(Stock, Signal.stock_id == Stock.id)
        .where(Stock.symbol == symbol.upper(), Signal.provider == provider)
        .order_by(Signal.date.desc())
        .limit(1)
    )


@router.get("/heatmap/{date_str}")
def get_signal_heatmap(date_str: str, db: DbSession) -> dict:
    """Get signal distribution heatmap for a date."""
    try:
        parsed_date = dt.date.fromisoformat(date_str)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.") from exc

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
    user: CurrentUser,
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
        logger.exception("backfill_all failed")
        raise HTTPException(status_code=500, detail="Backfill failed") from exc


@router.post("/backfill/{symbol}")
def backfill_signals(
    symbol: str,
    user: CurrentUser,
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
        # Data-quality block is an expected, client-actionable condition.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("backfill_symbol failed for %s", symbol)
        raise HTTPException(status_code=500, detail="Backfill failed") from exc


def _signal_to_fusion_input(signal: Signal | None) -> dict | None:
    """Adapt a persisted Signal row to the dict shape SignalFusionEngine expects."""
    if signal is None:
        return None
    return {
        "signal": signal.signal_type,
        "confidence": signal.confidence if signal.confidence is not None else 0.5,
        "probability": signal.value,
        "score": signal.value,
    }


@router.post("/fuse")
async def fuse_signal(
    user: CurrentUser,
    symbol: str = Query(..., min_length=1, max_length=20),
    db: Session = Depends(get_db),
):
    """
    Fuse technical + ML + sentiment signals into an actionable advisory.

    Risk enforcement is advisory-only: see ``risk_assessment.enforced``.
    """
    fusion_engine = SignalFusionEngine(db)
    feature_service = FeatureService(session=db)

    # Fetch the latest signal per provider via parameterized ORM queries.
    technical = _signal_to_fusion_input(_latest_signal(db, symbol, "technical"))
    ml = _signal_to_fusion_input(_latest_signal(db, symbol, "ml"))
    sentiment = _signal_to_fusion_input(_latest_signal(db, symbol, "sentiment"))

    # If we don't have an ML signal from normal channels, try to generate one from LSTM
    if ml is None:
        try:
            # Get the last 20 days of features for this symbol for LSTM sequence
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=20)
            features_dict = feature_service.compute_features_batch(
                symbol, start_date=start_date.isoformat(), end_date=end_date.isoformat()
            )
            if features_dict and "features" in features_dict:
                # features_dict["features"] should be a dict with feature names as keys
                # and lists of values over time as values
                features_data = features_dict["features"]
                if features_data and len(features_data) > 0:
                    # Convert to numpy array - we need to transpose to get [time_steps, features]
                    # Get the length of the time series (should be 20 if we have full data)
                    first_feature_key = next(iter(features_data))
                    time_series_length = len(features_data[first_feature_key])

                    if time_series_length > 0:
                        # Create array of shape [time_steps, num_features]
                        feature_arrays = []
                        for feature_name in features_data:
                            feature_arrays.append(features_data[feature_name])

                        # Transpose to get [time_steps, num_features]
                        features_array = np.array(feature_arrays).T.astype(np.float32)

                        # Generate LSTM signal
                        lstm_signal = fusion_engine.generate_lstm_signal_from_registry(
                            symbol, features_array
                        )
                        if lstm_signal is not None:
                            ml = {
                                "signal": lstm_signal["signal"],
                                "confidence": lstm_signal["confidence"],
                                "provider": "lstm",
                            }
        except Exception as e:
            logger.warning(f"Could not generate LSTM signal for {symbol}: {e}")
            # Continue without ML signal - fusion engine will handle insufficient signals

    # Infer regime (not yet implemented; default neutral-bull).
    regime = "bull"

    risk_mgr = RiskManager(db)
    risk_state = await risk_mgr.get_risk_state()

    fused = await fusion_engine.fuse(
        symbol=symbol,
        date=datetime.now(UTC),
        technical_signal=technical,
        ml_signal=ml,
        sentiment_signal=sentiment,
        regime=regime,
        risk_state=str(risk_state.value),
    )

    risk_assessment = dict(fused.risk_assessment)
    # Risk guardrails are stubbed (no live portfolio source); flag them as not enforced
    # so callers never mistake the advisory for real risk control.
    risk_assessment["enforced"] = False

    delivered = await signal_stream_publisher.publish_signal(
        symbol=fused.symbol,
        signal=fused.signal.value,
        confidence=float(fused.confidence),
        metadata={
            "risk_state": risk_state.value,
            "actionable": fused.is_actionable(),
        },
    )

    response = {
        "symbol": fused.symbol,
        "signal": fused.signal.value,
        "confidence": fused.confidence,
        "explanation": fused.explanation,
        "risk_assessment": risk_assessment,
        "raw_scores": fused.raw_scores,
        "weights_used": fused.weights_used,
        "is_actionable": fused.is_actionable(),
        "timestamp": fused.date.isoformat(),
        "stream_delivered": delivered,
    }
    return response


@router.post("/demo-broadcast")
async def demo_broadcast_signal(
    user: CurrentUser,
    symbol: str = Query(..., min_length=1, max_length=20),
    signal: str = Query("HOLD", pattern="^(BUY|SELL|HOLD)$"),
    confidence: float = Query(0.5, ge=0.0, le=1.0),
):
    """Broadcast a demo signal payload to websocket subscribers."""
    delivered = await signal_stream_publisher.publish_signal(
        symbol=symbol,
        signal=signal,
        confidence=confidence,
        metadata={"source": "demo-broadcast", "user_id": getattr(user, "id", None)},
    )
    return {
        "status": "ok",
        "delivered": delivered,
        "symbol": symbol.upper(),
        "signal": signal.upper(),
    }


@router.get("/risk-state")
async def get_risk_state(user: CurrentUser, db: Session = Depends(get_db)):
    """Get current system risk state.

    NOTE: ``enforced`` is False — the underlying drawdown/daily-loss/data-quality checks
    are not yet wired to a live portfolio source, so this state is advisory only.
    """
    risk_mgr = RiskManager(db)
    state = await risk_mgr.get_risk_state()
    kill_switch = await risk_mgr.kill_switch_active()

    return {
        "risk_state": state.value,
        "kill_switch_active": kill_switch,
        "advisory_status": "HOLD_ONLY" if kill_switch else "NORMAL",
        "enforced": False,
    }


@router.post("/position-size")
async def calculate_position_size(
    user: CurrentUser,
    symbol: str,
    signal: str,
    portfolio_equity: Annotated[float, Query(gt=0)],
    atr: Annotated[float, Query(gt=0)],
    db: Session = Depends(get_db),
):
    """Calculate max safe position size given current risk state.

    Advisory only: ``enforced`` is False until risk gates query live portfolio state.
    """
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
        "enforced": False,
    }
