import datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class HolidayCalendar(Base):
    __tablename__ = "holiday_calendar"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(255), nullable=True)  # type: ignore[assignment]
    is_trading_holiday: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_trading_day: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class DataTrust(Base):
    __tablename__ = "data_trust"

    __table_args__ = (
        CheckConstraint("trust_score >= 0.0 AND trust_score <= 1.0", name="ck_trust_score_range"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_id: Mapped[int] = mapped_column(Integer, nullable=False)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    trust_score: Mapped[float] = mapped_column(Float, nullable=False)
    completeness_score: Mapped[float] = mapped_column(Float, nullable=True)  # type: ignore[assignment]
    volume_anomaly_detected: Mapped[bool] = mapped_column(Boolean, nullable=True)  # type: ignore[assignment]
    missing_dates_count: Mapped[int] = mapped_column(Integer, nullable=True)  # type: ignore[assignment]
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=True)  # type: ignore[assignment]
    details: Mapped[str] = mapped_column(Text, nullable=True)  # type: ignore[assignment]


class DataQualityReport(Base):
    __tablename__ = "data_quality_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, unique=True)
    total_symbols: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    symbols_passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    symbols_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_trust_score: Mapped[float] = mapped_column(Float, nullable=True)  # type: ignore[assignment]
    total_rejected_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_missing_dates: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_volume_anomalies: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    details: Mapped[str] = mapped_column(Text, nullable=True)  # type: ignore[assignment]
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class DataQualityAlert(Base):

    __tablename__ = "data_quality_alerts"

    __table_args__ = (
        CheckConstraint("severity IN ('critical', 'warning', 'info')", name="ck_alert_severity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(Integer, nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=True)  # type: ignore[assignment]
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class SystemModeHistory(Base):
    __tablename__ = "system_mode_history"

    __table_args__ = (
        CheckConstraint(
            "mode IN ('NORMAL', 'DEGRADED', 'SAFE_MODE')", name="ck_system_mode"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    unsafe_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    total_symbols: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
