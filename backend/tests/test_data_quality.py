from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.data_quality import HolidayCalendar
from backend.app.models.price import Price
from backend.app.models.stock import Stock
from backend.app.services.data_quality import DataQualityService


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


def test_trust_score_perfect_data(db_session: Session) -> None:
    _seed_price(db_session, "NABIL", "2024-06-01", close=100.0, volume=1000)

    service = DataQualityService(session=db_session)
    result = service.evaluate_symbol_date("NABIL", "2024-06-01")

    assert result["trust_score"] > 0.7
    assert result["safe"] is True
    assert result["status"] == "excellent"
    assert "components" in result
    assert "completeness" in result["components"]
    assert "volume_score" in result["components"]


def test_trust_score_missing_volume_lowers_score(db_session: Session) -> None:
    _seed_price(db_session, "NICA", "2024-06-01", close=100.0, volume=1000)

    stock = db_session.scalar(select(Stock).where(Stock.symbol == "NICA"))
    price = db_session.scalar(
        select(Price).where(
            Price.stock_id == stock.id, Price.date == date(2024, 6, 1)
        )
    )
    price.volume = None
    db_session.commit()

    service = DataQualityService(session=db_session)
    result = service.evaluate_symbol_date("NICA", "2024-06-01")

    assert result["trust_score"] < 1.0
    assert result["details"]["completeness_score"] < 1.0
    assert result["components"]["completeness_penalty"] == -0.1


def test_volume_anomaly_detected(db_session: Session) -> None:
    _seed_price(db_session, "GBIME", "2024-06-01", close=100.0, volume=1000)
    _seed_price(db_session, "GBIME", "2024-06-02", close=101.0, volume=1100)
    _seed_price(db_session, "GBIME", "2024-06-03", close=102.0, volume=900)
    _seed_price(db_session, "GBIME", "2024-06-04", close=103.0, volume=1050)
    _seed_price(db_session, "GBIME", "2024-06-05", close=104.0, volume=950)
    _seed_price(db_session, "GBIME", "2024-06-06", close=105.0, volume=1000000)

    service = DataQualityService(session=db_session)
    result = service.evaluate_symbol_date("GBIME", "2024-06-06")

    assert result["details"]["volume_anomaly"] is True
    assert result["components"]["volume_score"] == 0.8
    assert result["components"]["volume_penalty"] == -0.2
    assert result["trust_score"] < 0.8


def test_holiday_reduces_trust(db_session: Session) -> None:
    db_session.add(
        HolidayCalendar(
            date=date(2024, 6, 1),
            description="Test Holiday",
            is_trading_holiday=True,
            is_trading_day=False,
        )
    )
    db_session.commit()
    _seed_price(db_session, "UPPER", "2024-06-01", close=100.0, volume=1000)

    service = DataQualityService(session=db_session)
    result = service.evaluate_symbol_date("UPPER", "2024-06-01")

    assert result["details"]["is_holiday"] is True
    assert result["details"]["is_trading_day"] is False
    assert result["trust_score"] < 1.0


def test_missing_dates_detected(db_session: Session) -> None:
    _seed_price(db_session, "NLIC", "2024-06-01", close=100.0, volume=1000)
    _seed_price(db_session, "NLIC", "2024-06-03", close=102.0, volume=1000)

    service = DataQualityService(session=db_session)
    result = service.evaluate_symbol_date("NLIC", "2024-06-03")

    assert result["details"]["missing_dates_count"] >= 1
    assert result["components"]["missing_penalty"] < 0


def test_daily_report_generation(db_session: Session) -> None:
    _seed_price(db_session, "NABIL", "2024-06-01", close=100.0, volume=1000)
    _seed_price(db_session, "NICA", "2024-06-01", close=100.0, volume=1000)

    service = DataQualityService(session=db_session)
    report = service.generate_daily_report("2024-06-01")

    assert report["report_date"] == "2024-06-01"
    assert report["total_symbols"] >= 2


def test_is_data_safe_threshold(db_session: Session) -> None:
    _seed_price(db_session, "NABIL", "2024-06-01", close=100.0, volume=1000)

    service = DataQualityService(session=db_session)
    assert service.is_data_safe("NABIL", "2024-06-01") is True


def test_symbol_quality_summary(db_session: Session) -> None:
    _seed_price(db_session, "NABIL", "2024-06-01", close=100.0, volume=1000)
    _seed_price(db_session, "NABIL", "2024-06-02", close=101.0, volume=1000)
    _seed_price(db_session, "NABIL", "2024-06-03", close=102.0, volume=1000)

    service = DataQualityService(session=db_session)
    service.evaluate_symbol_date("NABIL", "2024-06-01")
    service.evaluate_symbol_date("NABIL", "2024-06-02")
    service.evaluate_symbol_date("NABIL", "2024-06-03")
    summary = service.get_symbol_quality_summary("NABIL")

    assert summary["symbol"] == "NABIL"
    assert summary["total_records"] >= 3
    assert "avg_trust_score" in summary
    assert "unsafe_days" in summary
    assert "warning_days" in summary
    assert "excellent_days" in summary
    assert "common_issues" in summary


def test_warning_zone_classification(db_session: Session) -> None:
    _seed_price(db_session, "TEST", "2024-06-01", close=100.0, volume=1000)

    service = DataQualityService(session=db_session)
    result = service.evaluate_symbol_date("TEST", "2024-06-01")

    assert result["status"] in ("excellent", "warning", "unsafe")
    if result["trust_score"] >= 0.85:
        assert result["status"] == "excellent"
    elif result["trust_score"] >= 0.7:
        assert result["status"] == "warning"
    else:
        assert result["status"] == "unsafe"


def test_rolling_volume_anomaly(db_session: Session) -> None:
    for i in range(25):
        _seed_price(
            db_session, "ROLL", f"2024-06-{i+1:02d}", close=100.0, volume=1000
        )
    _seed_price(
        db_session, "ROLL", "2024-06-26", close=100.0, volume=10000000
    )

    service = DataQualityService(session=db_session)
    result = service.evaluate_symbol_date("ROLL", "2024-06-26")

    assert result["details"]["volume_anomaly"] is True
    assert result["trust_score"] < 0.8


def test_is_trading_day_persisted(db_session: Session) -> None:
    db_session.add(
        HolidayCalendar(
            date=date(2024, 6, 1),
            description="Saturday",
            is_trading_holiday=True,
            is_trading_day=False,
        )
    )
    db_session.commit()

    service = DataQualityService(session=db_session)
    holiday, trading_day = service._is_holiday(db_session, date(2024, 6, 1))

    assert holiday is True
    assert trading_day is False
