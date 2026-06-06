import datetime
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Numeric, UniqueConstraint, desc
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base
from backend.app.models.types import big_int_pk_type


class Price(Base):
    __tablename__ = "prices"
    __table_args__ = (
        UniqueConstraint("stock_id", "date", name="uq_prices_stock_id_date"),
        Index("ix_prices_stock_id_date_desc", "stock_id", desc("date")),
    )

    id: Mapped[int] = mapped_column(big_int_pk_type, primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False)
    date: Mapped[datetime.date] = mapped_column(Date, index=True, nullable=False)
    open: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=True)  # type: ignore[assignment]
    high: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=True)  # type: ignore[assignment]
    low: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=True)  # type: ignore[assignment]
    close: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=True)  # type: ignore[assignment]
    volume: Mapped[int] = mapped_column(nullable=True)  # type: ignore[assignment]

    stock = relationship("Stock", back_populates="prices")
