from datetime import datetime
from decimal import Decimal

from app.db.base import Base
from app.models.types import big_int_pk_type
from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(big_int_pk_type, primary_key=True)
    backtest_id: Mapped[int] = mapped_column(ForeignKey("backtests.id"), nullable=False)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    transaction_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=True)
    fill_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=True)
