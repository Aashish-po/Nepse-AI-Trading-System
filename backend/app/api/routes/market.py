from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.ingestion import IngestionRequest
from backend.app.schemas.market import PriceIngestRequest, PriceResponse
from backend.app.services.ingestion import IngestionService
from backend.app.services.market import ingest_price, list_prices

router = APIRouter(prefix="/market", tags=["market"])
DbSession = Annotated[Session, Depends(get_db)]
PriceLimit = Annotated[int, Query(ge=1, le=1000)]
PriceOffset = Annotated[int, Query(ge=0)]


@router.get("/prices", response_model=list[PriceResponse])
def get_prices(
    db: DbSession,
    symbol: str | None = None,
    limit: PriceLimit = 100,
    offset: PriceOffset = 0,
) -> list[PriceResponse]:
    rows = list_prices(db, symbol=symbol, limit=limit, offset=offset)
    return [
        PriceResponse(
            symbol=stock.symbol,
            date=price.date,
            open=price.open,
            high=price.high,
            low=price.low,
            close=price.close,
            volume=price.volume,
        )
        for price, stock in rows
    ]


@router.post("/ingest", response_model=PriceResponse, status_code=status.HTTP_201_CREATED)
def ingest_market_price(payload: PriceIngestRequest, db: DbSession) -> PriceResponse:
    price = ingest_price(db, payload)
    return PriceResponse(
        symbol=payload.symbol.upper(),
        date=price.date,
        open=price.open,
        high=price.high,
        low=price.low,
        close=price.close,
        volume=price.volume,
    )


@router.post("/ingest/batch", status_code=status.HTTP_202_ACCEPTED)
def ingest_batch(
    payload: IngestionRequest,
    symbol: str,
    db: DbSession,
) -> dict[str, object]:
    service = IngestionService(source=payload.source)
    result = service.run(
        symbol=symbol,
        start_date=payload.start_date,
        end_date=payload.end_date,
        dry_run=payload.dry_run,
    )
    return {"symbol": symbol.upper(), **result}
