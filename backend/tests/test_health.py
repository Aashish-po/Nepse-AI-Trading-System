def test_health_endpoint_returns_research_only_status(client) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["scope"] == "research-only"
