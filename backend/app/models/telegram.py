import datetime

from app.db.base import Base
from app.models.types import big_int_pk_type
from sqlalchemy import Boolean, Date, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class TelegramDailyAlert(Base):
    __tablename__ = "telegram_daily_alerts"

    id: Mapped[int] = mapped_column(big_int_pk_type, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    alert_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    telegram_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    delivery_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    alert_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_error: Mapped[str] = mapped_column(Text, nullable=True)
    last_sent_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.datetime.now
    )
