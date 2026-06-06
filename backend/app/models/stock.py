from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class Stock(Base):
    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=True)  # type: ignore[assignment]
    sector: Mapped[str] = mapped_column(String(100), nullable=True)  # type: ignore[assignment]
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    prices = relationship("Price", back_populates="stock")
