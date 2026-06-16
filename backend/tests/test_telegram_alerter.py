import datetime as dt

from app.models.data_quality import DataTrust
from app.models.price import Price
from app.models.stock import Stock
from app.models.telegram import TelegramDailyAlert
from app.services.telegram_alerter import TelegramAlerter


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
    trust = DataTrust(
        stock_id=stock.id,
        symbol=symbol,
        date=trade_date,
        trust_score=0.9,
        trust_version="v1",
        completeness_score=1.0,
        volume_anomaly_detected=False,
        missing_dates_count=0,
        rejected_count=0,
        details="{}",
    )
    db_session.add(trust)
    db_session.flush()
    return stock.id


def test_daily_cap_blocks_after_max_alerts(db_session):
    symbol = "TEST"
    trade_date = dt.date(2025, 1, 1)
    _seed_price(db_session, symbol, trade_date)

    alerter = TelegramAlerter(daily_cap=2, session=db_session)

    alert_date = trade_date
    db_session.add(
        TelegramDailyAlert(
            symbol=symbol,
            alert_date=alert_date,
            telegram_sent=True,
            delivery_status="sent",
            alert_count=2,
            last_error=None,
            last_sent_at=dt.datetime.now(dt.UTC),
        )
    )
    db_session.commit()

    result = alerter.resolve_signal(
        symbol, trade_date.isoformat(), "entry", 102.0, 0.9, session=db_session
    )
    assert result.status == "skipped"
    assert result.reason == "daily_cap_reached"


def test_daily_alert_count_is_enforced_by_alert_date(db_session):
    symbol = "CAP"
    trade_date = dt.date.today()
    _seed_price(db_session, symbol, trade_date)

    alerter = TelegramAlerter(daily_cap=2, session=db_session)

    first = alerter.resolve_signal(
        symbol, trade_date.isoformat(), "entry", 102.0, 0.9, session=db_session
    )
    second = alerter.resolve_signal(
        symbol, trade_date.isoformat(), "entry", 103.0, 0.9, session=db_session
    )
    third = alerter.resolve_signal(
        symbol, trade_date.isoformat(), "entry", 104.0, 0.9, session=db_session
    )

    assert first.status == "sent"
    assert second.status == "sent"
    assert third.status == "skipped"
    assert third.reason == "daily_cap_reached"

    alert = db_session.query(TelegramDailyAlert).one()
    assert alert.alert_count == 2


def test_provider_quota_status_counts(db_session):
    symbol = "TEST"
    trade_date = dt.date.today()
    stock_id = _seed_price(db_session, symbol, trade_date)

    from app.models.signal import Signal

    signal = Signal(
        stock_id=stock_id,
        date=trade_date,
        signal_type="entry",
        value=102.0,
        confidence=0.9,
        provider="rules",
        inference_cost=0.01,
        token_count=100,
    )
    db_session.add(signal)
    db_session.commit()

    alerter = TelegramAlerter(session=db_session)
    status = alerter.provider_quota_status("rules")
    assert status["signal_count"] >= 1
    assert status["cost"] >= 0.01
    assert status["token_count"] >= 100


def test_provider_quota_usage_is_recorded(db_session):
    symbol = "QUOTA"
    trade_date = dt.date.today()
    _seed_price(db_session, symbol, trade_date)

    alerter = TelegramAlerter(session=db_session)
    result = alerter.resolve_signal(
        symbol,
        trade_date.isoformat(),
        "entry",
        102.0,
        0.9,
        provider="rules",
        inference_cost=0.02,
        token_count=50,
        session=db_session,
    )

    assert result.status == "sent"
    status = alerter.provider_quota_status("rules", session=db_session)
    assert status["request_count"] == 1
    assert status["signal_count"] >= 1
    assert status["cost"] >= 0.02
    assert status["quota_token_count"] >= 50
