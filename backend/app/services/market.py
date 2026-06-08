from collections.abc import Sequence

from app.models.price import Price
from app.models.stock import Stock
from app.schemas.market import PriceIngestRequest
from sqlalchemy import select
from sqlalchemy.orm import Session


def get_or_create_stock(db: Session, payload: PriceIngestRequest) -> Stock:
    symbol = payload.symbol.upper()
    stock = db.scalar(select(Stock).where(Stock.symbol == symbol))
    if stock is not None:
        return stock

    stock = Stock(symbol=symbol, name=payload.name, sector=payload.sector)
    db.add(stock)
    db.flush()
    return stock


def ingest_price(db: Session, payload: PriceIngestRequest) -> Price:
    stock = get_or_create_stock(db, payload)
    price = Price(
        stock_id=stock.id,
        date=payload.date,
        open=payload.open,
        high=payload.high,
        low=payload.low,
        close=payload.close,
        volume=payload.volume,
    )
    db.add(price)
    db.commit()
    db.refresh(price)
    return price


def list_prices(
    db: Session,
    symbol: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> Sequence[tuple[Price, Stock]]:
    query = select(Price, Stock).join(Stock, Price.stock_id == Stock.id).order_by(Price.date.desc())
    if symbol:
        query = query.where(Stock.symbol == symbol.upper())
    return [tuple(row) for row in db.execute(query.limit(limit).offset(offset)).all()]
