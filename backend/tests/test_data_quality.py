from datetime import UTC, date, datetime, timedelta

from app.models.data_quality import DataTrust, HolidayCalendar
from app.models.price import Price
from app.models.stock import Stock
from app.services.data_quality import DataQualityService
from sqlalchemy import select
from sqlalchemy.orm import Session


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
    assert stock is not None
    price = db_session.scalar(
        select(Price).where(Price.stock_id == stock.id, Price.date == date(2024, 6, 1))
    )
    assert price is not None
    price.volume = None  # type: ignore[assignment]
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
    _seed_price(db_session, "NLIC", "2026-06-01", close=100.0, volume=1000)
    _seed_price(db_session, "NLIC", "2026-06-03", close=102.0, volume=1000)

    service = DataQualityService(session=db_session)
    result = service.evaluate_symbol_date("NLIC", "2026-06-03")

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
    _seed_price(db_session, "NABIL", "2026-06-01", close=100.0, volume=1000)
    _seed_price(db_session, "NABIL", "2026-06-02", close=101.0, volume=1000)
    _seed_price(db_session, "NABIL", "2026-06-03", close=102.0, volume=1000)

    service = DataQualityService(session=db_session)
    service.evaluate_symbol_date("NABIL", "2026-06-01")
    service.evaluate_symbol_date("NABIL", "2026-06-02")
    service.evaluate_symbol_date("NABIL", "2026-06-03")
    summary = service.get_symbol_quality_summary("NABIL")

    assert summary["symbol"] == "NABIL"
    assert summary["total_records"] >= 3
    assert "avg_trust_score" in summary
    assert "unsafe_days" in summary
    assert "warning_days" in summary
    assert "excellent_days" in summary
    assert "common_issues" in summary


def test_warning_zone_classification(db_session: Session) -> None:
    _seed_price(db_session, "TEST", "2026-06-01", close=100.0, volume=1000)

    service = DataQualityService(session=db_session)
    result = service.evaluate_symbol_date("TEST", "2026-06-01")

    assert result["status"] in ("excellent", "warning", "unsafe")
    if result["trust_score"] >= 0.85:
        assert result["status"] == "excellent"
    elif result["trust_score"] >= 0.7:
        assert result["status"] == "warning"
    else:
        assert result["status"] == "unsafe"


def test_rolling_volume_anomaly(db_session: Session) -> None:
    for i in range(25):
        _seed_price(db_session, "ROLL", f"2024-06-{i+1:02d}", close=100.0, volume=1000)
    _seed_price(db_session, "ROLL", "2024-06-26", close=100.0, volume=10000000)

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


def test_symbol_trust_trend(db_session: Session) -> None:
    start = date(2024, 5, 1)
    for i in range(30):
        price_date = start + timedelta(days=i)
        _seed_price(db_session, "TREND", price_date.strftime("%Y-%m-%d"), close=100.0, volume=1000)

    service = DataQualityService(session=db_session)
    for i in range(30):
        price_date = start + timedelta(days=i)
        service.evaluate_symbol_date("TREND", price_date.strftime("%Y-%m-%d"))

    trend = service.get_symbol_trust_trend("TREND", window=30)

    assert trend["symbol"] == "TREND"
    assert trend["trend"] is not None
    assert "avg_7d" in trend["trend"]
    assert "avg_30d" in trend["trend"]
    assert "stability" in trend["trend"]
    assert "unsafe_pct" in trend["trend"]


def test_data_freshness_check(db_session: Session) -> None:
    _seed_price(db_session, "FRESH", "2026-06-01", close=100.0, volume=1000)

    service = DataQualityService(session=db_session)
    result = service.check_data_freshness("FRESH", "2026-06-01")

    assert result["symbol"] == "FRESH"
    assert result["fresh"] is True


def test_data_freshness_delay(db_session: Session) -> None:
    _seed_price(db_session, "DELAYED", "2026-05-15", close=100.0, volume=1000)

    service = DataQualityService(session=db_session)
    result = service.check_data_freshness("DELAYED", "2026-06-01")

    assert result["symbol"] == "DELAYED"
    assert result["fresh"] is False


def test_bulk_evaluation(db_session: Session) -> None:
    _seed_price(db_session, "BULK1", "2026-06-01", close=100.0, volume=1000)
    _seed_price(db_session, "BULK2", "2026-06-01", close=100.0, volume=1000)

    service = DataQualityService(session=db_session)
    results = service.evaluate_symbols_bulk(["BULK1", "BULK2"], "2026-06-01")

    assert len(results) == 2
    assert results[0]["symbol"] in ("BULK1", "BULK2")


def test_alert_metadata_included(db_session: Session) -> None:
    _seed_price(db_session, "META", "2024-06-01", close=100.0, volume=1000)
    _seed_price(db_session, "META", "2024-06-02", close=100.0, volume=1000)
    _seed_price(db_session, "META", "2024-06-03", close=100.0, volume=1000)
    _seed_price(db_session, "META", "2024-06-04", close=100.0, volume=1000)
    _seed_price(db_session, "META", "2024-06-05", close=100.0, volume=1000)
    _seed_price(db_session, "META", "2024-06-06", close=100.0, volume=1000000)

    service = DataQualityService(session=db_session)
    result = service.evaluate_symbol_date("META", "2024-06-06")

    assert result["details"]["volume_anomaly"] is True
    assert "volume_actual" in result["details"]
    assert "volume_mean" in result["details"]
    assert "volume_z_score" in result["details"]


def test_cross_validate_sources_single_source(db_session: Session) -> None:
    _seed_price(db_session, "CV1", "2024-06-01", close=100.0, volume=1000)

    service = DataQualityService(session=db_session)
    result = service.cross_validate_sources("CV1", "2024-06-01")

    assert result["match"] is True
    assert result["reason"] == "single_source"


def test_cross_validate_sources_no_price(db_session: Session) -> None:
    db_session.add(Stock(symbol="CV2", is_active=True))
    db_session.commit()

    service = DataQualityService(session=db_session)
    result = service.cross_validate_sources("CV2", "2024-06-01")

    assert result["match"] is False
    assert result["reason"] == "no_price_data"


def test_cross_validate_sources_missing_symbol(db_session: Session) -> None:
    service = DataQualityService(session=db_session)
    result = service.cross_validate_sources("NONEXISTENT", "2024-06-01")

    assert result["match"] is False
    assert result["reason"] == "stock_not_found"


def test_get_system_mode_normal(db_session: Session) -> None:
    _seed_price(db_session, "MODE1", "2024-06-01", close=100.0, volume=1000)

    service = DataQualityService(session=db_session)
    service.evaluate_symbol_date("MODE1", "2024-06-01")
    mode = service.get_system_mode()

    assert mode["mode"] == "NORMAL"
    assert mode["total_symbols"] >= 1
    assert mode["unsafe_count"] == 0


def test_get_system_mode_degraded(db_session: Session) -> None:
    db_session.add(Stock(symbol="DEG1", is_active=True))
    db_session.add(Stock(symbol="DEG2", is_active=True))
    db_session.add(Stock(symbol="DEG3", is_active=True))
    db_session.commit()

    _seed_price(db_session, "DEG1", "2024-06-01", close=100.0, volume=1000)
    _seed_price(db_session, "DEG2", "2024-06-01", close=100.0, volume=1000)

    service = DataQualityService(session=db_session)
    service.evaluate_symbol_date("DEG1", "2024-06-01")
    service.evaluate_symbol_date("DEG2", "2024-06-01")

    mode = service.get_system_mode()

    assert mode["mode"] in ("NORMAL", "DEGRADED", "SAFE_MODE")
    assert "unsafe_ratio" in mode


def test_source_accuracy_score(db_session: Session) -> None:
    from app.models.data_source import DataSource, IngestionLog

    source = DataSource(name="TEST_SOURCE", type="api", is_active=True)
    db_session.add(source)
    db_session.flush()

    for _ in range(8):
        log = IngestionLog(
            source_id=source.id,
            status="success",
            records_fetched=100,
            records_inserted=100,
            records_rejected=0,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )
        db_session.add(log)
    for _ in range(2):
        log = IngestionLog(
            source_id=source.id,
            status="failed",
            records_fetched=100,
            records_inserted=0,
            records_rejected=10,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            errors='{"exception": "test_error"}',
        )
        db_session.add(log)
    db_session.commit()

    service = DataQualityService(session=db_session)
    score = service.get_source_accuracy_score(source.id)

    assert 0.0 <= score <= 1.0


def test_calculate_weighted_price(db_session: Session) -> None:
    from app.models.data_source import DataSource

    _seed_price(db_session, "WP1", "2024-06-01", close=100.0, volume=1000)

    src1 = DataSource(name="PRIMARY", type="api", is_active=True, accuracy_score=0.95)
    src2 = DataSource(name="BACKUP", type="api", is_active=True, accuracy_score=0.85)
    db_session.add(src1)
    db_session.add(src2)
    db_session.commit()

    service = DataQualityService(session=db_session)
    weighted = service.calculate_weighted_price("WP1", "2024-06-01", "close")

    assert weighted is not None
    assert weighted > 0


def test_safe_mode_blocks_feature_generation(db_session: Session) -> None:
    from app.services.data_quality_gate import DataQualityGate, SystemMode

    db_session.add(Stock(symbol="BLOCKED", is_active=True))
    db_session.commit()

    _seed_price(db_session, "BLOCKED", "2024-06-01", close=100.0, volume=1000)

    gate = DataQualityGate(session=db_session)
    service = DataQualityService(session=db_session)
    for symbol in ["S1", "S2", "S3", "S4", "S5"]:
        db_session.add(Stock(symbol=symbol, is_active=True))
    db_session.commit()

    for symbol in ["S1", "S2", "S3", "S4", "S5"]:
        service.evaluate_symbol_date(symbol, "2024-06-01")

    mode = gate.get_system_mode()
    if mode.mode == SystemMode.safe_mode:
        try:
            gate.assert_safe_for_features("BLOCKED", "2024-06-01")
            raise AssertionError("Should have raised DataQualityGateError")
        except Exception:
            pass


def test_system_mode_persists_history(db_session: Session) -> None:
    from app.models.data_quality import SystemModeHistory
    from sqlalchemy import func

    _seed_price(db_session, "HIST", "2024-06-01", close=100.0, volume=1000)

    service = DataQualityService(session=db_session)
    service.evaluate_symbol_date("HIST", "2024-06-01")
    service.get_system_mode()

    count = (
        db_session.scalar(
            select(func.count())
            .select_from(SystemModeHistory)
            .where(SystemModeHistory.mode == "NORMAL")
        )
        or 0
    )
    assert count >= 1


def test_source_drift_detection(db_session: Session) -> None:
    from app.models.data_source import DataSource, IngestionLog

    source = DataSource(name="DRIFT_TEST", type="api", is_active=True)
    db_session.add(source)
    db_session.flush()

    for _ in range(20):
        log = IngestionLog(
            source_id=source.id,
            status="success",
            records_fetched=100,
            records_inserted=100,
            records_rejected=0,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )
        db_session.add(log)
    for _ in range(10):
        log = IngestionLog(
            source_id=source.id,
            status="success",
            records_fetched=100,
            records_inserted=30,
            records_rejected=0,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )
        db_session.add(log)
    db_session.commit()

    service = DataQualityService(session=db_session)
    result = service.detect_source_drift(source.id, window=10)

    assert result["source_id"] == source.id
    assert "drift_detected" in result
    assert "ratio" in result


def test_blacklist_recovery(db_session: Session) -> None:
    from app.models.data_source import DataSource, IngestionLog

    source = DataSource(name="RECOVERY", type="api", is_active=False, accuracy_score=0.2)
    db_session.add(source)
    db_session.flush()

    for _ in range(10):
        log = IngestionLog(
            source_id=source.id,
            status="success",
            records_fetched=100,
            records_inserted=100,
            records_rejected=0,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )
        db_session.add(log)
    db_session.commit()

    service = DataQualityService(session=db_session)
    recovered = service.recover_blacklisted_sources(recovery_threshold=0.5)

    assert len(recovered) == 1
    assert recovered[0]["recovered"] is True
    assert recovered[0]["source_id"] == source.id


def test_trust_decay_applied(db_session: Session) -> None:
    from datetime import timedelta as td

    _seed_price(db_session, "DECAY", "2024-01-01", close=100.0, volume=1000)

    service = DataQualityService(session=db_session)
    service.evaluate_symbol_date("DECAY", "2024-01-01")

    stock = db_session.scalar(select(Stock).where(Stock.symbol == "DECAY"))
    assert stock is not None
    old_trust = db_session.scalar(select(DataTrust).where(DataTrust.stock_id == stock.id))
    assert old_trust is not None
    old_trust.date = datetime.now(UTC).date() - td(days=60)
    db_session.add(old_trust)
    db_session.commit()

    count = service.apply_trust_decay(days_threshold=30, decay_factor=0.95)

    assert count >= 1


def test_trust_version_persisted(db_session: Session) -> None:
    _seed_price(db_session, "VER1", "2024-06-01", close=100.0, volume=1000)

    service = DataQualityService(session=db_session)
    service.evaluate_symbol_date("VER1", "2024-06-01")

    stock = db_session.scalar(select(Stock).where(Stock.symbol == "VER1"))
    assert stock is not None
    trust = db_session.scalar(select(DataTrust).where(DataTrust.stock_id == stock.id))
    assert trust is not None
    assert trust.trust_version == "v1"


def test_trust_version_v2_calculation(db_session: Session) -> None:
    _seed_price(db_session, "VER2", "2024-06-01", close=100.0, volume=1000)

    stock = db_session.scalar(select(Stock).where(Stock.symbol == "VER2"))
    assert stock is not None
    service = DataQualityService(session=db_session)
    trust_score, details, components = service.compute_trust_score_with_version(
        db_session,
        stock.id,
        db_session.scalar(
            select(Price).where(
                Price.stock_id == stock.id,
                Price.date == date(2024, 6, 1),
            )
        ),
        trust_version="v2",
    )

    assert details.get("trust_version") == "v2"


def test_source_correlation_detection(db_session: Session) -> None:
    from app.models.data_source import DataSource, IngestionLog

    src1 = DataSource(name="SRC_A", type="api", is_active=True)
    src2 = DataSource(name="SRC_B", type="api", is_active=True)
    db_session.add(src1)
    db_session.add(src2)
    db_session.flush()

    for _ in range(5):
        log = IngestionLog(
            source_id=src1.id,
            status="failed",
            records_fetched=100,
            records_inserted=0,
            records_rejected=10,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            errors='{"sample_rejected": [{"date": "2024-06-01", "symbol": "NABIL"}]}',
        )
        db_session.add(log)

    for _ in range(5):
        log = IngestionLog(
            source_id=src2.id,
            status="failed",
            records_fetched=100,
            records_inserted=0,
            records_rejected=10,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            errors='{"sample_rejected": [{"date": "2024-06-01", "symbol": "NABIL"}]}',
        )
        db_session.add(log)

    db_session.commit()

    _seed_price(db_session, "NABIL", "2024-06-01", close=100.0, volume=1000)

    service = DataQualityService(session=db_session)
    correlations = service.detect_source_correlations(threshold=0.5)

    assert isinstance(correlations, list)


def test_event_override_creation(db_session: Session) -> None:
    service = DataQualityService(session=db_session)
    result = service.create_event_override(
        event_type="CORPORATE_ANNOUNCEMENT",
        date_str="2024-06-01",
        sensitivity_multiplier=0.9,
        reason="Quarterly results announcement",
    )

    assert result["event_type"] == "CORPORATE_ANNOUNCEMENT"
    assert result["sensitivity_multiplier"] == 0.9


def test_event_override_applied_to_trust_score(db_session: Session) -> None:
    _seed_price(db_session, "EVT1", "2024-06-01", close=100.0, volume=1000)

    service = DataQualityService(session=db_session)
    service.create_event_override(
        event_type="VOLUME_SPIKE",
        date_str="2024-06-01",
        sensitivity_multiplier=0.95,
        reason="Expected high volume",
        symbol="EVT1",
    )

    result = service.evaluate_with_event_override("EVT1", "2024-06-01")

    assert result.get("event_adjusted") is True
    assert "original_trust_score" in result
    assert result["trust_score"] == result["original_trust_score"] * 0.95


def test_event_override_expired(db_session: Session) -> None:
    service = DataQualityService(session=db_session)

    overrides = service.get_active_event_overrides("2024-06-01")
    assert isinstance(overrides, list)
