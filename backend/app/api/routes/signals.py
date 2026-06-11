"""Signal heatmap API routes."""

import datetime as dt
from typing import Annotated

import sqlalchemy as sa
from app.db.session import get_db
from app.models.signal import Signal
from app.models.stock import Stock
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

router = APIRouter(prefix="/signals", tags=["signals"])
DbSession = Annotated[Session, Depends(get_db)]


@router.get("/heatmap/{date_str}")
def get_signal_heatmap(date_str: str, db: DbSession) -> dict:
    """Get signal distribution heatmap for a date."""
    # Validate date format
    try:
        parsed_date = dt.date.fromisoformat(date_str)
    except ValueError:
        return {"error": "Invalid date format. Use YYYY-MM-DD."}

    # Get signals for the date with symbol info
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

    heat_data = [
        {
            "symbol": row.symbol,
            "signal_type": row.signal_type,
            "value": float(row.value) if row.value else 0.0,
            "confidence": float(row.confidence) if row.confidence else None,
        }
        for row in rows
    ]

    return {"date": date_str, "heat_data": heat_data}
