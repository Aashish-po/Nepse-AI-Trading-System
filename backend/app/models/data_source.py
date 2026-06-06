from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class DataSource(Base):
    __tablename__ = "data_sources"

    __table_args__ = (
        CheckConstraint("type IN ('api', 'scraper', 'csv')", name="ck_data_sources_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False, default="api")
    priority: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    accuracy_score: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


class IngestionLog(Base):
    __tablename__ = "ingestion_logs"

    __table_args__ = (
        CheckConstraint("status IN ('success', 'failed')", name="ck_ingestion_logs_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(100), nullable=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="failed")
    records_fetched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_inserted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_rejected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=True)
    errors: Mapped[str] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
