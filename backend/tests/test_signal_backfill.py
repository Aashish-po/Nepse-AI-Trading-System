import datetime as dt

from app.models.price import Price
from app.models.stock import Stock
from app.services.signal_backfill import SignalBackfillService


def _seed_price(db_session, symbol: str, trade_date: dt.date) -> int:
    stock = Stock(symbol=symbol, is_active=True)
    db_session.add(stock)
    db_session.flush()
    price = Price(
        stock_id=stock.id,
        date=trade_date,
        open=100.0,
        high=105.0,
        low=99.0,
        close=102.0,
        volume=1000,
    )
    db_session.add(price)
    db_session.commit()
    return stock.id


def test_signal_backfill_base_and_idempotent(db_session):
    symbol = "BACKFILL"
    base_date = dt.date(2024, 6, 10)
    _seed_price(db_session, symbol, base_date)

    entry_rules = [{"rule": "rsi_oversold", "params": {"threshold": 30}}]

    svc = SignalBackfillService(session=db_session)
    result = svc.backfill_symbol(
        symbol,
        start_date=base_date.isoformat(),
        end_date=base_date.isoformat(),
        entry_rules=entry_rules,
        upsert=True,
    )
    assert result["created"] >= 0
    second = svc.backfill_symbol(
        symbol,
        start_date=base_date.isoformat(),
        end_date=base_date.isoformat(),
        entry_rules=entry_rules,
        upsert=True,
    )
    assert second["created"] == 0
