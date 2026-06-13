"""Signal heatmap and backfill API routes."""

import datetime as dt
from typing import Annotated

import sqlalchemy as sa
from app.db.session import get_db
from app.models.signal import Signal
from app.models.stock import Stock
from app.schemas.signals import ProviderQuotaResponse, ProviderQuotaSummaryResponse
from app.services.data_quality_gate import DataQualityGateError
from app.services.provider_quota import ProviderQuotaService
from app.services.signal_backfill import SignalBackfillService
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
