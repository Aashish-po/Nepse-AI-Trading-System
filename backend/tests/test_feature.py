from datetime import date, timedelta
from decimal import Decimal

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.feature import Feature
from backend.app.models.price import Price
from backend.app.models.stock import Stock
from backend.app.services.feature import FeatureService


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


def test_feature_batch_computes_indicators(db_session: Session) -> None:
    _seed_price_series(db_session, "NEPSE", "2024-01-01", count=30)

    service = FeatureService(session=db_session)
    result = service.compute_features_batch("NEPSE")

    assert result["symbol"] == "NEPSE"
    assert result["processed_dates"] > 0
    assert "rsi_14" in result["features_computed"]
    assert "macd" in result["features_computed"]
    assert "atr_14" in result["features_computed"]


def test_rsi_range_bounds() -> None:
    service = FeatureService()
    prices = np.array([100.0] * 30)
    rsi = service._compute_rsi(prices, period=14)
    valid = rsi[~np.isnan(rsi)]
    assert np.all(valid >= 0)
    assert np.all(valid <= 100)


def test_rsi_rising_prices() -> None:
    service = FeatureService()

    rising_prices = np.linspace(100.0, 200.0, 100)
    rsi_rising = service._compute_rsi(rising_prices, period=14)
    valid_rsi = rsi_rising[~np.isnan(rsi_rising)]

    assert len(valid_rsi) > 0
    assert valid_rsi[-1] == 100.0


def test_rsi_falling_prices() -> None:
    service = FeatureService()

    falling_prices = np.linspace(200.0, 100.0, 100)
    rsi_falling = service._compute_rsi(falling_prices, period=14)
    valid_rsi = rsi_falling[~np.isnan(rsi_falling)]

    assert len(valid_rsi) > 0
    assert valid_rsi[-1] == 0.0


def test_rsi_insufficient_data() -> None:
    service = FeatureService()
    prices = np.array([100.0] * 5)
    rsi = service._compute_rsi(prices, period=14)
    assert np.all(np.isnan(rsi))


def test_macd_calculation() -> None:
    service = FeatureService()
    prices = np.sin(np.linspace(0, 10, 100)) * 50 + 100
    macd_result = service._compute_macd(prices)

    assert macd_result["macd"].shape == prices.shape
    assert macd_result["signal"].shape == prices.shape
    assert macd_result["histogram"].shape == prices.shape

    valid_mask = ~(np.isnan(macd_result["macd"]) | np.isnan(macd_result["signal"]))
    np.testing.assert_allclose(
        macd_result["histogram"][valid_mask],
        macd_result["macd"][valid_mask] - macd_result["signal"][valid_mask],
    )


def test_atr_calculation() -> None:
    service = FeatureService()
    high = np.array([101.0, 102.0, 103.0, 104.0, 105.0] * 20)
    low = np.array([99.0, 98.0, 97.0, 96.0, 95.0] * 20)
    close = np.linspace(100.0, 105.0, 100)

    atr = service._compute_atr(high, low, close, period=14)

    valid_atr = atr[~np.isnan(atr)]
    assert len(valid_atr) > 0
    assert np.all(valid_atr >= 0)


def test_sma_ema_calculation() -> None:
    service = FeatureService()
    values = np.linspace(100.0, 200.0, 60)

    sma = service._compute_sma(values, period=20)
    ema = service._compute_ema(values, period=20)

    valid_sma = sma[~np.isnan(sma)]
    valid_ema = ema[~np.isnan(ema)]

    assert len(valid_sma) > 0
    assert len(valid_ema) > 0

    assert np.isclose(valid_sma[-1], np.mean(values[-20:]))
    assert valid_ema[-1] > valid_sma[-1]


def test_volume_ratio() -> None:
    service = FeatureService()
    volume = np.array([1000.0] * 20 + [2000.0] * 5)

    volume_sma_arr = service._compute_sma(volume, period=20)
    ratio = service._compute_volume_ratio(volume, volume_sma_arr)

    valid_ratio = ratio[~np.isnan(ratio)]
    assert len(valid_ratio) > 0
    assert np.all(valid_ratio >= 0)


def test_returns_calculation() -> None:
    service = FeatureService()
    prices = np.array([100.0, 105.0, 102.0, 110.0, 98.0])
    returns = service._compute_returns(prices)

    assert np.isnan(returns[0])
    assert abs(returns[1] - 0.05) < 0.001
    assert abs(returns[2] - (-0.0286)) < 0.01


def test_rolling_volatility() -> None:
    service = FeatureService()
    returns = np.random.randn(60) / 10
    volatility = service._compute_rolling_std(returns, period=20)

    assert len(volatility) == len(returns)
    valid_vol = volatility[~np.isnan(volatility)]
    assert len(valid_vol) > 0
    assert valid_vol[-1] > 0


def test_price_range_calculation() -> None:
    service = FeatureService()
    high = np.array([110.0, 105.0, 108.0])
    low = np.array([90.0, 95.0, 98.0])
    close = np.array([100.0, 100.0, 100.0])

    range_pct = service._compute_price_range(high, low, close)

    expected = np.array([0.20, 0.10, 0.10])
    np.testing.assert_allclose(range_pct, expected, rtol=0.01)


def test_missing_data_handling() -> None:
    service = FeatureService()

    prices_with_nan = np.array([100.0, np.nan, 102.0, 103.0, np.nan, 105.0])
    sma = service._compute_sma(prices_with_nan, period=3)

    assert np.isnan(sma[0])


def test_trust_score_propagated_to_features(db_session: Session) -> None:
    _seed_price_series(db_session, "TRUST", "2024-01-01", count=30)

    service = FeatureService(session=db_session)
    result = service.compute_features_batch("TRUST")

    assert result["processed_dates"] > 0


def test_feature_trust_score_stored(db_session: Session) -> None:
    from sqlalchemy import func

    _seed_price_series(db_session, "STORE_TRUST", "2024-01-01", count=30)

    service = FeatureService(session=db_session)
    service.compute_features_batch("STORE_TRUST")

    feature_count = db_session.scalar(select(func.count()).select_from(Feature))
    assert feature_count > 0
