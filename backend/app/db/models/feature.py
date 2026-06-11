import datetime

from app.db.base import Base
from app.db.models.types import big_int_pk_type, json_dict_type
from sqlalchemy import Date, Float, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class Feature(Base):
    __tablename__ = "features"
    __table_args__ = (
        UniqueConstraint(
            "stock_id", "date", "feature_version", name="uq_features_stock_date_version"
        ),
        Index("ix_features_stock_id_date", "stock_id", "date"),
    )

    id: Mapped[int] = mapped_column(big_int_pk_type, primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    feature_version: Mapped[str] = mapped_column(String(50), nullable=False)
    trust_score: Mapped[float] = mapped_column(Float, nullable=True)
    trust_version: Mapped[str] = mapped_column(String(20), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=True)
    features_meta: Mapped[dict] = mapped_column(json_dict_type, nullable=True)
    values: Mapped[dict] = mapped_column(json_dict_type, nullable=False)
