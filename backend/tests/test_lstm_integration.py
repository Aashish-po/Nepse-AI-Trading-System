from datetime import date, timedelta
from decimal import Decimal

import numpy as np
from app.models.price import Price
from app.models.stock import Stock
from app.services.feature import FeatureService
from sqlalchemy import select
from sqlalchemy.orm import Session

from ml.dataset import DatasetBuilder


def _seed_price_series(
    db: Session,
    symbol: str,
    start_date: str,
    count: int = 60,
    base_price: float = 100.0,
) -> int:
    stock = db.scalar(select(Stock).where(Stock.symbol == symbol.upper()))
    if stock is None:
        stock = Stock(symbol=symbol.upper(), is_active=True)
        db.add(stock)
        db.flush()
    start = date.fromisoformat(start_date)
    for i in range(count):
        price_date = start + timedelta(days=i)
        close = base_price + (i - count / 2) * 0.5 + np.random.randn() * 2
        high = close + abs(np.random.randn()) * 1
        low = close - abs(np.random.randn()) * 1
        db.add(
            Price(
                stock_id=stock.id,
                date=price_date,
                open=Decimal(str(max(1.0, close * 0.99))),
                high=Decimal(str(high)),
                low=Decimal(str(low)),
                close=Decimal(str(close)),
                volume=int(1000 + abs(np.random.randn()) * 500),
            )
        )
    db.commit()
    return stock.id


def _seed_features(db: Session, symbol: str) -> None:
    service = FeatureService(session=db)
    service.compute_features_batch(symbol)


def test_lstm_dataset_build_nabil(db_session):
    _seed_price_series(db_session, "NABIL", "2024-01-01", count=100)
    _seed_features(db_session, "NABIL")
    builder = DatasetBuilder(session=db_session)

    bundle = builder.build(symbol="NABIL")

    assert bundle is not None
    assert bundle.X_train is not None
    assert bundle.X_val is not None
    assert bundle.y_train is not None
    assert bundle.y_val is not None

    assert len(bundle.X_train) > 0
    assert len(bundle.X_val) > 0
    assert bundle.X_train.shape[1] > 0
