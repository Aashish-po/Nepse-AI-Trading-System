from sqlalchemy.orm import Session

from backend.app.services.ingestion import IngestionService


def test_ingestion_inserts_data(db_session: Session) -> None:
    service = IngestionService(source="test", session=db_session)
    result = service.run("TEST")

    assert result["fetched"] > 0
    assert result["inserted"] > 0
    assert result["rejected"] == 0


def test_duplicate_ingestion_is_idempotent(db_session: Session) -> None:
    service = IngestionService(source="test", session=db_session)
    first = service.run("TEST2")
    second = service.run("TEST2")

    assert first["inserted"] > 0
    assert second["inserted"] == 0


def test_validation_rejects_bad_rows(db_session: Session) -> None:
    service = IngestionService(source="test", session=db_session)
    bad_data = [
        {
            "date": "2024-01-01",
            "open": 200,
            "high": 100,
            "low": 50,
            "close": 150,
            "volume": -1,
        }
    ]
    valid, rejected = service._validate(bad_data)

    assert len(valid) == 0
    assert len(rejected) == 1
    assert "error" in rejected[0]
