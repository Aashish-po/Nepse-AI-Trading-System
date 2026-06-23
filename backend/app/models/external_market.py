"""External market symbols and OHLCV prices (Marketstack / Finnhub, etc.).

These are *separate* from the NEPSE ``Price`` table: they hold global/benchmark
market data fetched from external providers for advisory context features, and
must never be confused with primary NEPSE prices. ``ExternalPrice`` is unique on
``(provider, external_symbol, date)`` so re-ingestion is idempotent.
``ExternalSymbol.mapped_nepse_symbol`` optionally links a provider ticker to a
NEPSE symbol once coverage is validated.
"""

from __future__ import annotations

import datetime

from app.db.base import Base
from app.models.types import json_dict_type
from sqlalchemy import (
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column


class ExternalSymbol(Base):
    __tablename__ = "external_symbols"
    __table_args__ = (
        UniqueConstraint("provider", "external_symbol", name="uq_external_symbols_provider_symbol"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    external_symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    asset_class: Mapped[str | None] = mapped_column(String(30), nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    country: Mapped[str | None] = mapped_column(String(50), nullable=True)
    exchange: Mapped[str | None] = mapped_column(String(50), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mapped_nepse_symbol: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ExternalPrice(Base):
    __tablename__ = "external_prices"
    __table_args__ = (
        UniqueConstraint(
            "provider", "external_symbol", "date", name="uq_external_prices_provider_symbol_date"
        ),
        Index("ix_external_prices_provider_symbol_date", "provider", "external_symbol", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    external_symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    open: Mapped[float | None] = mapped_column(Float, nullable=True)
    high: Mapped[float | None] = mapped_column(Float, nullable=True)
    low: Mapped[float | None] = mapped_column(Float, nullable=True)
    close: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    raw_json: Mapped[dict] = mapped_column(json_dict_type, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
