"""Macro-economic series and observations (e.g. FRED).

These tables store point-in-time macro data fetched from external providers.
``MacroObservation`` is unique on ``(macro_series_id, date)`` so re-ingestion is
idempotent. ``fetched_at`` records when we retrieved the value, supporting
point-in-time-safe feature generation.
"""

from __future__ import annotations

import datetime

from app.db.base import Base
from app.models.types import json_dict_type
from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship


class MacroSeries(Base):
    __tablename__ = "macro_series"
    __table_args__ = (
        UniqueConstraint("provider", "series_id", name="uq_macro_series_provider_series"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    series_id: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    units: Mapped[str | None] = mapped_column(String(100), nullable=True)
    frequency: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    observations: Mapped[list[MacroObservation]] = relationship(
        back_populates="series", cascade="all, delete-orphan"
    )


class MacroObservation(Base):
    __tablename__ = "macro_observations"
    __table_args__ = (
        UniqueConstraint("macro_series_id", "date", name="uq_macro_obs_series_date"),
        Index("ix_macro_obs_series_date", "macro_series_id", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    macro_series_id: Mapped[int] = mapped_column(
        ForeignKey("macro_series.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False, index=True)
    value: Mapped[float] = mapped_column(Float, nullable=True)  # null = explicitly missing
    raw_json: Mapped[dict] = mapped_column(json_dict_type, nullable=True)
    fetched_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    series: Mapped[MacroSeries] = relationship(back_populates="observations")
