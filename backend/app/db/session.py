# backend/app/db/session.py
from collections.abc import Generator
from typing import Any

from app.core.config import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Database engine
is_sqlite = "sqlite" in settings.database_url
engine_kwargs: dict[str, Any] = {"echo": False}
if is_sqlite:
    # SQLite uses a single-connection pool that doesn't accept pool_size/max_overflow
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs["pool_size"] = settings.database_pool_size
    engine_kwargs["max_overflow"] = 20
    engine_kwargs["pool_pre_ping"] = True

engine = create_engine(settings.database_url, **engine_kwargs)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Dependency for FastAPI to get DB session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
