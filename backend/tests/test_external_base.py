"""Tests for the external-provider HTTP client base (Commit 0 foundation).

All tests are offline: network is provided via ``httpx.MockTransport`` and time
is injected (fake clock/sleep) so retry/rate-limit behaviour is deterministic.
"""

from __future__ import annotations

import httpx
import pytest
from app.services.external.base import (
    ExternalApiClient,
    ExternalApiError,
    ExternalApiRateLimitError,
    ExternalApiUnauthorizedError,
    redact,
)


class _FakeClock:
    """Monotonic clock that only advances when sleep() is called."""

    def __init__(self) -> None:
        self.t = 0.0
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds


def _client(handler, **kwargs) -> ExternalApiClient:
    clock = kwargs.pop("clock", None) or _FakeClock()
    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport)
    return ExternalApiClient(
        provider="test",
        base_url="https://example.test",
        client=http,
        clock=clock.now,
        sleep=clock.sleep,
        backoff_base=0.1,
        **kwargs,
    )


def test_get_json_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "path": request.url.path})

    client = _client(handler)
    data = client.get_json("/v1/thing", params={"a": "1"})
    assert data["ok"] is True
    assert data["path"] == "/v1/thing"


def test_unauthorized_raises_immediately() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, json={"error": "bad key"})

    client = _client(handler)
    with pytest.raises(ExternalApiUnauthorizedError):
        client.get_json("/secure")
    assert calls["n"] == 1  # not retried


def test_rate_limit_retried_then_raises() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, json={"error": "slow down"})

    client = _client(handler, max_retries=3)
    with pytest.raises(ExternalApiRateLimitError):
        client.get_json("/limited")
    assert calls["n"] == 3  # exhausted all attempts


def test_server_error_retries_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, json={"error": "unavailable"})
        return httpx.Response(200, json={"ok": True})

    client = _client(handler, max_retries=5)
    data = client.get_json("/flaky")
    assert data["ok"] is True
    assert calls["n"] == 3


def test_timeout_is_retried() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 2:
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(200, json={"ok": True})

    client = _client(handler, max_retries=3)
    data = client.get_json("/slow")
    assert data["ok"] is True
    assert calls["n"] == 2


def test_non_retryable_4xx_raises_without_retry() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404, json={"error": "missing"})

    client = _client(handler)
    with pytest.raises(ExternalApiError):
        client.get_json("/missing")
    assert calls["n"] == 1


def test_rate_limiter_sleeps_when_window_full() -> None:
    clock = _FakeClock()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    client = _client(handler, clock=clock, rate_limit_per_minute=2)
    for _ in range(3):
        client.get_json("/x")
    # Third call must have waited for the 60s window to free a slot.
    assert any(s > 0 for s in clock.sleeps)


def test_api_key_sent_as_query_param_not_logged(caplog: pytest.LogCaptureFixture) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport)
    client = ExternalApiClient(
        provider="test",
        base_url="https://example.test",
        api_key="SUPER_SECRET",
        auth_query_param="api_key",
        client=http,
    )
    with caplog.at_level("DEBUG"):
        client.get_json("/data")
    assert seen.get("api_key") == "SUPER_SECRET"
    assert "SUPER_SECRET" not in caplog.text


def test_redact_masks_secret_keys() -> None:
    payload = {"api_key": "abc", "nested": {"token": "xyz", "safe": 1}, "list": [{"key": "k"}]}
    out = redact(payload)
    assert out["api_key"] == "***"
    assert out["nested"]["token"] == "***"
    assert out["nested"]["safe"] == 1
    assert out["list"][0]["key"] == "***"
