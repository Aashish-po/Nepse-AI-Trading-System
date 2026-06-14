import os
import sys
from collections.abc import Generator
from pathlib import Path

import pytest
from app.db.base import Base
from app.db.models import (  # noqa: F401 — ensure all DB model tables are registered
    Backtest,
    DataQualityAlert,
    DataQualityReport,
    Dataset,
    DataSource,
    DataTrust,
    EventOverride,
    Feature,
    HolidayCalendar,
    IngestionLog,
    ModelRegistry,
    PortfolioSnapshot,
    Price,
    Signal,
    SourceCorrelation,
    Stock,
    Strategy,
    SystemModeHistory,
    Trade,
    User,
)
from app.db.session import get_db
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Prevent model re-registration
os.environ["SQLALCHEMY_ECHO"] = "false"


@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine("sqlite:///./test.db", echo=False)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(db_engine) -> Generator[Session, None, None]:
    with db_engine.connect() as conn:
        transaction = conn.begin()
        session = sessionmaker(autocommit=False, autoflush=False, bind=conn)()
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()


@pytest.fixture
def client(db_session):
    from app.main import create_app

    test_app = create_app()

    def override_get_db():
        yield db_session

    test_app.dependency_overrides[get_db] = override_get_db
    with TestClient(test_app) as c:
        yield c
    test_app.dependency_overrides.pop(get_db, None)
