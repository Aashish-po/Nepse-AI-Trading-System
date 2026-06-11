"""Drift event persistence model."""

from __future__ import annotations

import sqlalchemy as sa
from app.db.base import Base
from app.db.models.types import json_dict_type
from sqlalchemy import Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func


class DriftEvent(Base):
    __tablename__ = "drift_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(50), nullable=True)
    feature: Mapped[str] = mapped_column(String(100), nullable=False)
    p_value: Mapped[float] = mapped_column(Float, nullable=True)
    psi: Mapped[float] = mapped_column(Float, nullable=True)
    is_drift: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    details: Mapped[dict] = mapped_column(json_dict_type, nullable=True)
    created_at: Mapped[sa.DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
