import os
import sys
from pathlib import Path

# ✅ ADD THIS FIRST - before any app imports
BACKEND_DIR = Path(__file__).parent.parent.resolve()
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Bind the global engine/SessionLocal to a dedicated test database *before*
# importing any app module. Service code opens its own SessionLocal() rather
# than receiving an injected session, so the tests and services must share the
# same database for seeded data to be visible across sessions.
os.environ["DATABASE_URL"] = "sqlite:///./test.db"

# Disable MLflow tracking during tests. A developer's local .env may point
# MLFLOW_TRACKING_URI at a server (e.g. http://localhost:5000) that is not
# running in CI/test, which would make the MLflow client retry for minutes and
# block backtest requests. Tests must not depend on an external tracking server.
os.environ["MLFLOW_ENABLED"] = "false"

from collections.abc import Generator  # noqa: E402

import app.models  # noqa: F401, E402  # registers all ORM models on Base.metadata
import pytest  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine, get_db  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema() -> Generator[None, None, None]:
    """Create all tables once for the whole test session."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def _truncate_all() -> None:
    """Remove every row from every table (including rows committed by service
    sessions) so each test starts from a clean slate."""
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture
def db_session(_schema) -> Generator[Session, None, None]:
    """Session per test backed by the shared test database.

    Data is committed (so service-created sessions can see it) and the tables
    are truncated before and after each test for isolation.
    """
    _truncate_all()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        _truncate_all()


@pytest.fixture
def setup_db(_schema):
    """Backward-compatible alias for tests that depend on schema creation."""
    yield


@pytest.fixture
def db(db_session) -> Session:
    """Backward-compatible alias for the per-test session."""
    return db_session


@pytest.fixture
def db_engine(_schema):
    """Backward-compatible accessor for the shared engine."""
    return engine


@pytest.fixture
def client(db_session):
    """FastAPI test client backed by the shared test session.

    Authentication is stubbed: mutating routes now require ``get_current_user``, so the
    fixture injects a fixed test user. Auth *enforcement* itself is covered separately in
    test_auth.py; route tests here run as an authenticated researcher.
    """
    from app.core.security import get_current_user
    from app.main import create_app
    from app.models.user import User

    test_app = create_app()

    def override_get_db():
        yield db_session

    def override_get_current_user():
        return User(
            id="test-user",
            email="test@example.com",
            hashed_password="x",
            role="researcher",
        )

    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[get_current_user] = override_get_current_user
    with TestClient(test_app) as c:
        yield c
    test_app.dependency_overrides.pop(get_db, None)
    test_app.dependency_overrides.pop(get_current_user, None)
