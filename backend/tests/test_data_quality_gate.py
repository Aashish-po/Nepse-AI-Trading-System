from datetime import date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.data_quality import HolidayCalendar
from backend.app.models.price import Price
from backend.app.models.stock import Stock
from backend.app.services.backtest import BacktestService
from backend.app.services.data_quality_gate import (
    DataQualityGate,
    DataQualityGateError,
    DataQualityStatus,
)
from backend.app.services.feature import FeatureService


def _seed_price(
    db: Session,
    symbol: str,
    price_date: str,
    close: float = 100.0,
    volume: int = 1000,
) -> None:
    stock = db.scalar(select(Stock).where(Stock.symbol == symbol.upper()))
    if stock is None:
        stock = Stock(symbol=symbol.upper(), is_active=True)
        db.add(stock)
        db.flush()
    db.add(
        Price(
            stock_id=stock.id,
            date=datetime.strptime(price_date, "%Y-%m-%d").date(),
            close=close,
            volume=volume,
        )
    )
    db.commit()


def test_feature_gate_blocks_nonexistent_symbol(db_session: Session) -> None:
    service = FeatureService(gate=DataQualityGate(session=db_session))
    with pytest.raises(DataQualityGateError):
        service.compute_features("NONEXISTENT", "2024-06-01")


def test_feature_gate_allows_safe_data(db_session: Session) -> None:
    _seed_price(db_session, "NABIL", "2024-06-01", close=100.0, volume=1000)

    service = FeatureService(gate=DataQualityGate(session=db_session))
    result = service.compute_features("NABIL", "2024-06-01")
    assert result["symbol"] == "NABIL"
    assert "features" in result


def test_backtest_gate_excludes_unsafe_dates(db_session: Session) -> None:
    _seed_price(db_session, "NABIL", "2024-06-01", close=100.0, volume=1000)
    _seed_price(db_session, "NABIL", "2024-06-02", close=101.0, volume=1000)
    _seed_price(db_session, "NABIL", "2024-06-03", close=102.0, volume=1000)
    _seed_price(db_session, "NABIL", "2024-06-04", close=103.0, volume=1000)
    _seed_price(db_session, "NABIL", "2024-06-05", close=104.0, volume=1000)
    db_session.add(
        HolidayCalendar(
            date=date(2024, 6, 1),
            description="Holiday",
            is_trading_holiday=True,
            is_trading_day=False,
        )
    )
    db_session.commit()

    service = BacktestService(gate=DataQualityGate(session=db_session))
    result = service.run_backtest("NABIL", "2024-06-01", "2024-06-05")

    assert result["symbol"] == "NABIL"
    assert result["included_days"] + result["excluded_days"] == 5
    if result["excluded_days"] > 0:
        assert "2024-06-01" in result["excluded_dates"]


def test_soft_mode_weight_for_warning_zone(db_session: Session) -> None:
    _seed_price(db_session, "TEST", "2024-06-01", close=100.0, volume=1000)
    db_session.add(
        HolidayCalendar(
            date=date(2024, 6, 1),
            description="Holiday",
            is_trading_holiday=True,
            is_trading_day=False,
        )
    )
    db_session.commit()

    gate = DataQualityGate(session=db_session)
    result = gate.check("TEST", "2024-06-01")

    weight = gate.get_feature_weight("TEST", "2024-06-01", base_weight=1.0)
    if result.status == DataQualityStatus.warning:
        assert weight == 0.5
    elif result.status == DataQualityStatus.unsafe:
        assert weight == 0.0
    else:
        assert weight == 1.0


def test_hard_gate_status_classification(db_session: Session) -> None:
    gate = DataQualityGate(session=db_session)

    nonexistent = gate.check("NONEXISTENT", "2024-06-01")
    assert nonexistent.status == DataQualityStatus.unsafe
    assert nonexistent.safe is False

    _seed_price(db_session, "SAFE", "2024-06-01", close=100.0, volume=1000)
    safe = gate.check("SAFE", "2024-06-01")
    assert safe.status in (DataQualityStatus.excellent, DataQualityStatus.warning)
    assert safe.trust_score >= 0.7
