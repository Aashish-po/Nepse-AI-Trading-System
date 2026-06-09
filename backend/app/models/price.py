import datetime
from decimal import Decimal

from app.db.base import Base
from app.models.types import big_int_pk_type
from sqlalchemy import Date, ForeignKey, Index, Numeric, UniqueConstraint, desc
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Price(Base):
    __tablename__ = "prices"
    __table_args__ = (
        UniqueConstraint("stock_id", "date", name="uq_prices_stock_id_date"),
        Index("ix_prices_stock_id_date_desc", "stock_id", desc("date")),
    )

    id: Mapped[int] = mapped_column(big_int_pk_type, primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False)
    date: Mapped[datetime.date] = mapped_column(Date, index=True, nullable=False)
    open: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=True)
    high: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=True)
    low: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=True)
    close: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=True)
    volume: Mapped[int] = mapped_column(nullable=True)

    stock = relationship("Stock", back_populates="prices")
