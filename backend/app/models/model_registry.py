from __future__ import annotations

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.models.types import json_dict_type


class ModelRegistry(Base):
    __tablename__ = "models"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(50), nullable=True)
    params: Mapped[dict] = mapped_column(json_dict_type, nullable=True)
    model_artifact_path: Mapped[str] = mapped_column(String(500), nullable=True)
    metrics: Mapped[dict] = mapped_column(json_dict_type, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
