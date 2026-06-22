"""Reusable HTTP client base for external research-data providers.

Provides a small, dependency-light wrapper around ``httpx.Client`` with:

* provider-specific error mapping (unauthorized / rate-limit / generic),
* a sliding-window rate limiter,
* retry with exponential backoff for *transient* failures only
  (HTTP 429, 5xx, and network/timeout errors),
* redacted logging that never emits API keys, and
* an injectable ``httpx.Client`` plus injectable clock/sleep for deterministic
  tests (no real time, no real network).

The clock and sleep callables are injectable because the test suite forbids
``time``-based nondeterminism; production code uses ``time.monotonic`` /
``time.sleep`` by default.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from collections.abc import Callable
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# httpx logs every request line at INFO, including the full URL. Providers that
# authenticate via a query parameter (e.g. FRED ``?api_key=``) would leak the key
# into logs. Raise httpx's own logger to WARNING so request URLs are never
# emitted; this module does its own redacted logging via ``_safe_url``/``redact``.
logging.getLogger("httpx").setLevel(logging.WARNING)

# Header/query parameter names whose values must never be logged.
_REDACT_KEYS = frozenset(
    {"token", "api_key", "apikey", "access_key", "key", "authorization", "x-api-key"}
)


class ExternalApiError(RuntimeError):
    """Base error for any external-provider failure."""

    def __init__(
        self, message: str, *, provider: str | None = None, status_code: int | None = None
    ):
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code


class ExternalApiUnauthorizedError(ExternalApiError):
    """Raised on HTTP 401/403 — missing, expired, or wrong-scope API key."""


class ExternalApiRateLimitError(ExternalApiError):
    """Raised on HTTP 429 once retries are exhausted."""


def redact(value: Any) -> Any:
    """Return ``value`` with any secret-looking keys masked, for safe logging."""
    if isinstance(value, dict):
        return {
            k: ("***" if str(k).lower() in _REDACT_KEYS else redact(v)) for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return type(value)(redact(v) for v in value)
    return value


class _SlidingWindowRateLimiter:
    """Allow at most ``max_calls`` within any rolling ``period`` seconds.

    ``acquire`` blocks (via the injected ``sleep``) only when the window is full.
    A non-positive ``max_calls`` disables limiting entirely.
    """

    def __init__(
        self,
        max_calls: int,
        period: float = 60.0,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._max_calls = max_calls
        self._period = period
        self._clock = clock
        self._sleep = sleep
        self._events: deque[float] = deque()

    def acquire(self) -> None:
        if self._max_calls <= 0:
            return
        now = self._clock()
        self._evict(now)
        if len(self._events) >= self._max_calls:
            wait = self._period - (now - self._events[0])
            if wait > 0:
                self._sleep(wait)
                now = self._clock()
                self._evict(now)
        self._events.append(now)

    def _evict(self, now: float) -> None:
        cutoff = now - self._period
        while self._events and self._events[0] <= cutoff:
            self._events.popleft()


class ExternalApiClient:
    """Base client for a single external provider.

    Subclasses/callers supply ``provider`` (label used in errors/logs/metrics),
    ``base_url``, and optional auth. Network access goes through an injected or
    lazily-created ``httpx.Client`` so tests can pass an ``httpx.MockTransport``.
    """

    # Retryable conditions: too-many-requests, server errors, network/timeouts.
    _RETRY_STATUS = frozenset({429, 500, 502, 503, 504})

    def __init__(
        self,
        provider: str,
        base_url: str,
        *,
        api_key: str | None = None,
        auth_header: str | None = None,
        auth_query_param: str | None = None,
        rate_limit_per_minute: int = 0,
        timeout: float = 15.0,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        client: httpx.Client | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key or ""
        self._auth_header = auth_header
        self._auth_query_param = auth_query_param
        self._timeout = timeout
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._sleep = sleep
        self._owns_client = client is None
        self._client = client if client is not None else httpx.Client(timeout=timeout)
        self._limiter = _SlidingWindowRateLimiter(
            rate_limit_per_minute, period=60.0, clock=clock, sleep=sleep
        )

    # -- lifecycle ----------------------------------------------------------
    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> ExternalApiClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- request plumbing ---------------------------------------------------
    def _auth_params(self, params: dict[str, Any]) -> dict[str, Any]:
        if self._auth_query_param and self._api_key:
            params = {**params, self._auth_query_param: self._api_key}
        return params

    def _auth_headers(self, headers: dict[str, str]) -> dict[str, str]:
        if self._auth_header and self._api_key:
            headers = {**headers, self._auth_header: self._api_key}
        return headers

    def get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """GET ``path`` and return parsed JSON, applying auth, rate limiting,
        retry/backoff, and error mapping."""
        url = path if path.startswith("http") else f"{self.base_url}/{path.lstrip('/')}"
        req_params = self._auth_params(dict(params or {}))
        req_headers = self._auth_headers(dict(headers or {}))

        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            self._limiter.acquire()
            try:
                response = self._client.get(url, params=req_params, headers=req_headers)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc
                logger.warning(
                    "external provider %s network error on %s (attempt %d/%d): %s",
                    self.provider,
                    self._safe_url(path),
                    attempt + 1,
                    self._max_retries,
                    type(exc).__name__,
                )
                self._backoff(attempt)
                continue

            mapped = self._map_status(response)
            if mapped is None:
                return response.json()

            # Retryable HTTP status (429/5xx) — back off and retry.
            last_exc = mapped
            if attempt < self._max_retries - 1:
                logger.warning(
                    "external provider %s status %s on %s (attempt %d/%d), retrying",
                    self.provider,
                    response.status_code,
                    self._safe_url(path),
                    attempt + 1,
                    self._max_retries,
                )
                self._backoff(attempt)
                continue
            raise mapped

        # Exhausted retries on a transient error.
        if isinstance(last_exc, ExternalApiError):
            raise last_exc
        raise ExternalApiError(
            f"{self.provider} request failed after {self._max_retries} attempts: "
            f"{type(last_exc).__name__ if last_exc else 'unknown'}",
            provider=self.provider,
        )

    def _map_status(self, response: httpx.Response) -> ExternalApiError | None:
        """Map a response to an error, or ``None`` if it is a success.

        Non-retryable client errors (401/403 and other 4xx) raise immediately;
        retryable statuses (429/5xx) are returned for the retry loop to handle.
        """
        code = response.status_code
        if code < 400:
            return None
        if code in (401, 403):
            raise ExternalApiUnauthorizedError(
                f"{self.provider} unauthorized (HTTP {code})",
                provider=self.provider,
                status_code=code,
            )
        if code == 429:
            return ExternalApiRateLimitError(
                f"{self.provider} rate limited (HTTP 429)",
                provider=self.provider,
                status_code=code,
            )
        if code in self._RETRY_STATUS:
            return ExternalApiError(
                f"{self.provider} server error (HTTP {code})",
                provider=self.provider,
                status_code=code,
            )
        # Other 4xx — not retryable.
        raise ExternalApiError(
            f"{self.provider} request error (HTTP {code})",
            provider=self.provider,
            status_code=code,
        )

    def _backoff(self, attempt: int) -> None:
        self._sleep(self._backoff_base * (2**attempt))

    def _safe_url(self, path: str) -> str:
        """Path for logging — never includes query params (which carry keys)."""
        return path.split("?", 1)[0]
