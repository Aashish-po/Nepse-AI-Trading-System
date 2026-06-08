from app.db.base import Base
from app.models.types import json_dict_type
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(50), nullable=False)
    params: Mapped[dict] = mapped_column(json_dict_type, nullable=True)
    split_metadata: Mapped[dict] = mapped_column(json_dict_type, nullable=True)
    dataset_metadata: Mapped[dict] = mapped_column("metadata", json_dict_type, nullable=True)
