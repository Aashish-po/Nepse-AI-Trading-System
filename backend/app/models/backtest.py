from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.models.types import json_dict_type


class Backtest(Base):
    __tablename__ = "backtests"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id"), nullable=False)
    config: Mapped[dict] = mapped_column(json_dict_type, nullable=False)
    metrics: Mapped[dict] = mapped_column(json_dict_type, nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
