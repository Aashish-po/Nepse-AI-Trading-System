from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.models.types import json_dict_type


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    config: Mapped[dict] = mapped_column(json_dict_type, nullable=False)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
