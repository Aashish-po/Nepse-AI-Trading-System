# backend/app/db/session.py
from collections.abc import Generator, Iterator
from contextlib import contextmanager
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
    # Fail fast when the database is unreachable instead of hanging on the
    # default ~15s libpq connect timeout. libpq treats values < 2 as 2s.
    engine_kwargs["connect_args"] = {"connect_timeout": settings.database_connect_timeout}

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


@contextmanager
def session_scope(*candidates: Session | None) -> Iterator[Session]:
    """Yield the first caller-supplied session, or a fresh one we own and close.

    Pass the candidate sessions in priority order (e.g. a method's optional
    ``session`` arg, then ``self._session``). If all are ``None`` we create a
    ``SessionLocal()`` and close it on exit; otherwise we borrow the caller's
    session and leave it open. Replaces the per-service
    ``owns_session``/``_get_session``/``close_session`` boilerplate.
    """
    existing = next((s for s in candidates if s is not None), None)
    session = existing or SessionLocal()
    try:
        yield session
    finally:
        if existing is None:
            session.close()
