from fastapi.testclient import TestClient

from backend.app.main import create_app


def test_health_endpoint_returns_research_only_status() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["scope"] == "research-only"

