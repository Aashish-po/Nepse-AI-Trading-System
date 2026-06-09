import datetime

from app.db.base import Base
from app.models.types import big_int_pk_type
from sqlalchemy import BigInteger, Date, Float, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class NEPSEIndex(Base):
    __tablename__ = "nepse_index"
    __table_args__ = (Index("ix_nepse_date", "date"),)

    id: Mapped[int] = mapped_column(big_int_pk_type, primary_key=True)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False, unique=True)
    open: Mapped[float] = mapped_column(Float, nullable=True)
    high: Mapped[float] = mapped_column(Float, nullable=True)
    low: Mapped[float] = mapped_column(Float, nullable=True)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=True)


class SectorIndex(Base):
    __tablename__ = "sector_indices"
    __table_args__ = (
        UniqueConstraint("sector", "date", name="uq_sector_date"),
        Index("ix_sector_sector_date", "sector", "date"),
    )

    id: Mapped[int] = mapped_column(big_int_pk_type, primary_key=True)
    sector: Mapped[str] = mapped_column(String(100), nullable=False)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=True)
    high: Mapped[float] = mapped_column(Float, nullable=True)
    low: Mapped[float] = mapped_column(Float, nullable=True)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=True)
