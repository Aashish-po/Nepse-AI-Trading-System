"""External research-data provider adapters.

Clients in this package fetch advisory, research-only data (macro series, news,
global market context) from third-party APIs. They are deliberately isolated
from model inference and signal fusion: external data is precomputed into the
database/feature store so inference stays deterministic and outage-safe.

Every provider is opt-in. With default settings (empty keys, ``*_ENABLED=false``)
no module here makes a network call.
"""

from app.services.external.base import (
    ExternalApiClient,
    ExternalApiError,
    ExternalApiRateLimitError,
    ExternalApiUnauthorizedError,
)

__all__ = [
    "ExternalApiClient",
    "ExternalApiError",
    "ExternalApiRateLimitError",
    "ExternalApiUnauthorizedError",
]
