"""External / macro API endpoint tests (offline)."""

from __future__ import annotations

from datetime import date

import httpx
from app.core.config import Settings
from app.services.external.fred import FredClient
from app.services.external_macro import MacroIngestionService


def test_external_health_lists_providers(client) -> None:
    resp = client.get("/external/health")
    assert resp.status_code == 200
    body = resp.json()
    keys = {p["key"] for p in body["providers"]}
    assert {"fred", "newsapi", "marketstack"}.issubset(keys)
    # No secret material in the payload.
    assert "api_key" not in resp.text.lower()


def test_unknown_provider_sync_returns_404(client) -> None:
    resp = client.post("/external/sync/nonsense")
    assert resp.status_code == 404


def test_macro_series_and_observations_endpoints(client, db_session) -> None:
    # Seed via the ingestion service (offline mock client).
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/series"):
            return httpx.Response(200, json={"seriess": [{"title": "10Y"}]})
        return httpx.Response(200, json={"observations": [{"date": "2024-01-01", "value": "4.0"}]})

    cfg = Settings(_env_file=None, FRED_ENABLED=True, FRED_API_KEY="k")  # type: ignore[call-arg]
    fred = FredClient(cfg, client=httpx.Client(transport=httpx.MockTransport(handler)))
    MacroIngestionService(cfg, session=db_session, client=fred).run(
        ["DGS10"], today=date(2024, 6, 1)
    )

    series_resp = client.get("/macro/series")
    assert series_resp.status_code == 200
    assert any(s["series_id"] == "DGS10" for s in series_resp.json())

    obs_resp = client.get("/macro/observations", params={"series_id": "DGS10"})
    assert obs_resp.status_code == 200
    rows = obs_resp.json()
    assert rows and rows[0]["value"] == 4.0

    missing = client.get("/macro/observations", params={"series_id": "NOPE"})
    assert missing.status_code == 404
