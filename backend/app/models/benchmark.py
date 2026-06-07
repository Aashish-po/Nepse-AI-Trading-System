import datetime

from sqlalchemy import BigInteger, Date, Float, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.models.types import big_int_pk_type


class NEPSEIndex(Base):
    __tablename__ = "nepse_index"

    id: Mapped[int] = mapped_column(big_int_pk_type, primary_key=True)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False, unique=True)
    open: Mapped[float] = mapped_column(Float, nullable=True)  # type: ignore[assignment]
    high: Mapped[float] = mapped_column(Float, nullable=True)  # type: ignore[assignment]
    low: Mapped[float] = mapped_column(Float, nullable=True)  # type: ignore[assignment]
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=True)  # type: ignore[assignment]

    __table_args__ = (Index("ix_nepse_date", "date"),)


class SectorIndex(Base):
    __tablename__ = "sector_indices"

    id: Mapped[int] = mapped_column(big_int_pk_type, primary_key=True)
    sector: Mapped[str] = mapped_column(String(100), nullable=False)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=True)  # type: ignore[assignment]
    high: Mapped[float] = mapped_column(Float, nullable=True)  # type: ignore[assignment]
    low: Mapped[float] = mapped_column(Float, nullable=True)  # type: ignore[assignment]
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=True)  # type: ignore[assignment]

    __table_args__ = (
        UniqueConstraint("sector", "date", name="uq_sector_date"),
        Index("ix_sector_sector_date", "sector", "date"),
    )
