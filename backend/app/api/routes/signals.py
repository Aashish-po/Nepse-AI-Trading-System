"""Signal heatmap and backfill API routes."""

import datetime as dt
from typing import Annotated

import sqlalchemy as sa
from app.db.session import get_db
from app.models.signal import Signal
from app.models.stock import Stock
from app.services.data_quality_gate import DataQualityGateError
from app.services.signal_backfill import SignalBackfillService
from fastapi import APIRouter, Depends
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
