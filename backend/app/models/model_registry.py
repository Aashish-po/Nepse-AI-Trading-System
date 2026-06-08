from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from app.db.base import Base
from app.models.types import json_dict_type
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column


class ModelRegistry(Base):
    __tablename__ = "models"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(50), nullable=True)
    params: Mapped[dict] = mapped_column(json_dict_type, nullable=True)
    model_artifact_path: Mapped[str] = mapped_column(String(500), nullable=True)
    metrics: Mapped[dict] = mapped_column(json_dict_type, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
