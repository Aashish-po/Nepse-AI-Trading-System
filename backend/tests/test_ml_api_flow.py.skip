"""Integration tests for ML → DB → API flow."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import numpy as np

# Avoid double-importing SQLAlchemy models with different module paths
# (this can cause "Table ... already defined" errors during metadata setup).
from app.db.base import Base  # noqa: F401
from app.models.price import Price
from app.models.stock import Stock
from app.services.feature import FEATURE_VERSION, FeatureService


def _seed_price_series(db_session, symbol: str, start_date: str, count: int = 80) -> None:
    stock = db_session.scalar(
        __import__("sqlalchemy").select(Stock).where(Stock.symbol == symbol.upper())
    )
    if stock is None:
        stock = Stock(symbol=symbol.upper(), is_active=True)
        db_session.add(stock)
        db_session.flush()

    start = date.fromisoformat(start_date)
    for i in range(count):
        price_date = start + timedelta(days=i)
        close = 100.0 + (i - count / 2) * 0.25 + np.random.randn() * 1.0
        high = close + abs(np.random.randn()) * 0.5
        low = close - abs(np.random.randn()) * 0.5
        db_session.add(
            Price(
                stock_id=stock.id,
                date=price_date,
                open=Decimal(str(max(1.0, close * 0.99))),
                high=Decimal(str(high)),
                low=Decimal(str(low)),
                close=Decimal(str(close)),
                volume=int(1000 + abs(np.random.randn()) * 200),
            )
        )

    db_session.commit()


def test_ml_db_api_flow_train_and_list_models(db_session, client) -> None:
    symbol = "FLOW"

    # 1) Seed DB with minimal market data
    _seed_price_series(db_session, symbol, "2024-01-01", count=100)

    # 2) Generate features (persisted to DB)
    FeatureService(session=db_session).compute_features_batch(symbol)

    # 3) Call API to train model (ML → DB persistence)
    train_resp = client.post(
        "/train",
        json={
            "symbol": symbol,
            "model_name": "logistic",
            "model_version": "1.0.0",
            "feature_version": FEATURE_VERSION,
            "horizon": 5,
        },
    )

    assert train_resp.status_code == 200
    payload = train_resp.json()
    assert payload["symbol"] == symbol
    assert payload["model_name"] == "logistic"
    assert payload["model_path"] is not None

    # 4) Verify DB → API model listing reflects persisted registry
    list_resp = client.get("/models")

    assert list_resp.status_code == 200

    models = list_resp.json()["models"]
    assert any(m["name"] == "logistic" and m["version"] == payload["model_version"] for m in models)
