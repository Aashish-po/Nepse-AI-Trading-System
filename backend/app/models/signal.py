import datetime

from sqlalchemy import Date, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.models.types import big_int_pk_type


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (Index("ix_signals_stock_id_date", "stock_id", "date"),)

    id: Mapped[int] = mapped_column(big_int_pk_type, primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    signal_type: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=True)