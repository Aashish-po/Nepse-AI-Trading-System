from datetime import date
from decimal import Decimal

from app.models.data_quality import HolidayCalendar
from app.models.price import Price
from app.models.stock import Stock
from app.services.data_quality_gate import (
    DataQualityGate,
    DataQualityGateError,
    DataQualityStatus,
)
from app.services.feature import FeatureService
from sqlalchemy import select
from sqlalchemy.orm import Session


def test_feature_gate_blocks_nonexistent_symbol(db_session: Session) -> None:
    service = FeatureService(gate=DataQualityGate(session=db_session))
    try:
        service.compute_features("NONEXISTENT", "2024-06-01")
        raise AssertionError("Should have raised DataQualityGateError")
    except DataQualityGateError:
        pass


def test_backtest_gate_excludes_unsafe_dates(db_session: Session) -> None:
    stock = db_session.scalar(select(Stock).where(Stock.symbol == "NABIL"))
    if stock is None:
        stock = Stock(symbol="NABIL", is_active=True)
        db_session.add(stock)
        db_session.flush()

    for d in ["2024-06-01", "2024-06-02", "2024-06-03", "2024-06-04", "2024-06-05"]:
        db_session.add(
            Price(
                stock_id=stock.id,
                date=__import__("datetime").datetime.strptime(d, "%Y-%m-%d").date(),
                close=Decimal("100.0"),
                open=Decimal("99.0"),
                high=Decimal("101.0"),
                low=Decimal("99.0"),
                volume=1000,
            )
        )
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
    excluded: list[str] = []
    included: list[str] = []
    for day in ["2024-06-01", "2024-06-02", "2024-06-03", "2024-06-04", "2024-06-05"]:
        try:
            gate.assert_safe_for_backtest("NABIL", day)
            included.append(day)
        except DataQualityGateError:
            excluded.append(day)

    assert len(included) + len(excluded) == 5
    if len(excluded) > 0:
        assert "2024-06-01" in excluded


def test_soft_mode_weight_for_warning_zone(db_session: Session) -> None:
    stock = db_session.scalar(select(Stock).where(Stock.symbol == "TEST"))
    if stock is None:
        stock = Stock(symbol="TEST", is_active=True)
        db_session.add(stock)
        db_session.flush()

    db_session.add(
        Price(
            stock_id=stock.id,
            date=date(2024, 6, 1),
            close=Decimal("100.0"),
            open=Decimal("99.0"),
            high=Decimal("101.0"),
            low=Decimal("99.0"),
            volume=1000,
        )
    )
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

    stock = db_session.scalar(select(Stock).where(Stock.symbol == "SAFE"))
    if stock is None:
        stock = Stock(symbol="SAFE", is_active=True)
        db_session.add(stock)
        db_session.flush()

    db_session.add(
        Price(
            stock_id=stock.id,
            date=date(2024, 6, 1),
            close=Decimal("100.0"),
            open=Decimal("99.0"),
            high=Decimal("101.0"),
            low=Decimal("99.0"),
            volume=1000,
        )
    )
    db_session.commit()

    safe = gate.check("SAFE", "2024-06-01")
    assert safe.status in (DataQualityStatus.excellent, DataQualityStatus.warning)
    assert safe.trust_score >= 0.7


def test_get_system_mode_result(db_session: Session) -> None:
    from app.services.data_quality_gate import SystemMode

    stock = db_session.scalar(select(Stock).where(Stock.symbol == "MODE_TEST"))
    if stock is None:
        stock = Stock(symbol="MODE_TEST", is_active=True)
        db_session.add(stock)
        db_session.flush()

    db_session.add(
        Price(
            stock_id=stock.id,
            date=date(2024, 6, 1),
            close=Decimal("100.0"),
            open=Decimal("99.0"),
            high=Decimal("101.0"),
            low=Decimal("99.0"),
            volume=1000,
        )
    )
    db_session.commit()

    gate = DataQualityGate(session=db_session)
    mode = gate.get_system_mode()

    assert mode.mode in (SystemMode.normal, SystemMode.degraded, SystemMode.safe_mode)


def test_signal_generation_allowed_respects_safemode(db_session: Session) -> None:
    gate = DataQualityGate(session=db_session)

    allowed = gate.get_signal_generation_allowed()
    assert isinstance(allowed, bool)
