from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from backend.app.models.price import Price
from backend.app.models.stock import Stock


def test_create_stock_insert_price_and_query(client) -> None:
    ingest_response = client.post(
        "/market/ingest",
        json={
            "symbol": "NABIL",
            "name": "Nabil Bank Limited",
            "sector": "Commercial Banks",
            "date": "2026-06-04",
            "open": "1000.00",
            "high": "1020.00",
            "low": "990.00",
            "close": "1010.00",
            "volume": 10000,
        },
    )

    assert ingest_response.status_code == 201
    assert ingest_response.json()["symbol"] == "NABIL"

    prices_response = client.get("/market/prices?symbol=NABIL")

    assert prices_response.status_code == 200
    assert prices_response.json()[0]["close"] == "1010.0000"


def test_price_unique_constraint_is_enforced(db_session) -> None:
    stock = Stock(symbol="NICA", name="NIC Asia Bank Limited", sector="Commercial Banks")
    db_session.add(stock)
    db_session.commit()
    db_session.refresh(stock)

    db_session.add_all(
        [
            Price(stock_id=stock.id, date=date(2026, 6, 4), close=900, volume=1000),
            Price(stock_id=stock.id, date=date(2026, 6, 4), close=901, volume=1001),
        ]
    )

    with pytest.raises(IntegrityError):
        db_session.commit()
