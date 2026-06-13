import datetime

from app.db.base import Base
from app.models.types import big_int_pk_type
from sqlalchemy import Date, DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON


class ProviderQuotaUsage(Base):
    __tablename__ = "provider_quota_usage"
    __table_args__ = (
        UniqueConstraint("provider", "quota_date", name="uq_provider_quota_date"),
        Index("ix_provider_quota_usage_quota_date", "quota_date"),
        Index("ix_provider_quota_usage_provider_quota_date", "provider", "quota_date"),
    )

    id: Mapped[int] = mapped_column(big_int_pk_type, primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    quota_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    signal_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    metadata_json = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.datetime.now(datetime.UTC)
    )
