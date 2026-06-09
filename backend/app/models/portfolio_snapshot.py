import datetime
from decimal import Decimal

from app.db.base import Base
from app.models.types import big_int_pk_type, json_dict_type
from sqlalchemy import Date, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(big_int_pk_type, primary_key=True)
    backtest_id: Mapped[int] = mapped_column(ForeignKey("backtests.id"), nullable=False)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    equity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    cash: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    positions: Mapped[dict] = mapped_column(json_dict_type, nullable=False)
