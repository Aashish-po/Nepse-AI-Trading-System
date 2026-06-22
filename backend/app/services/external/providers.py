"""Provider registry: a single source of truth for external providers.

Each entry maps a provider key to its config flags (enabled + key presence) and
default ``DataSource.accuracy_score``. Endpoints use this to report provider
health/availability; the seed helper materialises a ``DataSource`` row per
provider so ingestion logs can reference a stable source.
"""

from __future__ import annotations

from dataclasses import dataclass

import sqlalchemy as sa
from app.core.config import Settings, settings as default_settings
from app.models.data_source import DataSource
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class ProviderSpec:
    key: str  # canonical lowercase id, e.g. "fred"
    name: str  # DataSource.name, e.g. "FRED"
    role: str  # short human description
    enabled_attr: str  # Settings attribute holding the enabled flag
    key_attr: str | None  # Settings attribute holding the API key (None = keyless)
    default_accuracy: float


# Ordered by rollout priority (must-use first, optional scale last).
PROVIDERS: tuple[ProviderSpec, ...] = (
    ProviderSpec("fred", "FRED", "macro series", "fred_enabled", "fred_api_key", 0.95),
    ProviderSpec(
        "newsapi", "NEWSAPI", "news headlines", "newsapi_enabled", "newsapi_api_key", 0.70
    ),
    ProviderSpec(
        "huggingface",
        "HUGGINGFACE",
        "hosted NLP",
        "huggingface_enabled",
        "huggingface_api_key",
        0.75,
    ),
    ProviderSpec(
        "marketstack",
        "MARKETSTACK",
        "global OHLCV",
        "marketstack_enabled",
        "marketstack_api_key",
        0.80,
    ),
    ProviderSpec(
        "finnhub", "FINNHUB", "candles/fundamentals", "finnhub_enabled", "finnhub_api_key", 0.80
    ),
    ProviderSpec("polygon", "POLYGON", "market data", "polygon_enabled", "polygon_api_key", 0.85),
    ProviderSpec(
        "iexcloud", "IEXCLOUD", "US equities", "iexcloud_enabled", "iexcloud_api_key", 0.80
    ),
    ProviderSpec("coingecko", "COINGECKO", "crypto regime", "coingecko_enabled", None, 0.70),
    ProviderSpec("fixer", "FIXER", "FX rates", "fixer_enabled", "fixer_api_key", 0.80),
    ProviderSpec(
        "exchangerate_host",
        "EXCHANGERATE_HOST",
        "FX fallback",
        "exchangerate_host_enabled",
        None,
        0.70,
    ),
)

PROVIDERS_BY_KEY: dict[str, ProviderSpec] = {p.key: p for p in PROVIDERS}


def is_enabled(spec: ProviderSpec, cfg: Settings | None = None) -> bool:
    """A provider is usable only when its flag is on AND (if it needs one) a key is set."""
    cfg = cfg or default_settings
    if not getattr(cfg, spec.enabled_attr):
        return False
    if spec.key_attr is not None and not getattr(cfg, spec.key_attr):
        return False
    return True


def has_key(spec: ProviderSpec, cfg: Settings | None = None) -> bool:
    cfg = cfg or default_settings
    if spec.key_attr is None:
        return True
    return bool(getattr(cfg, spec.key_attr))


def provider_status(cfg: Settings | None = None) -> list[dict[str, object]]:
    """Return a serialisable status row per provider (no secrets)."""
    cfg = cfg or default_settings
    return [
        {
            "key": p.key,
            "name": p.name,
            "role": p.role,
            "enabled_flag": bool(getattr(cfg, p.enabled_attr)),
            "has_key": has_key(p, cfg),
            "usable": is_enabled(p, cfg),
        }
        for p in PROVIDERS
    ]


def ensure_data_source(session: Session, spec: ProviderSpec) -> DataSource:
    """Idempotently return (creating if needed) the ``DataSource`` for a provider."""
    existing = session.scalar(sa.select(DataSource).where(DataSource.name == spec.name))
    if existing is not None:
        return existing
    ds = DataSource(
        name=spec.name,
        type="api",
        priority=1,
        is_active=True,
        accuracy_score=spec.default_accuracy,
    )
    session.add(ds)
    session.flush()
    return ds


def ensure_all_data_sources(session: Session) -> int:
    """Seed a ``DataSource`` row for every provider. Returns count created."""
    created = 0
    for spec in PROVIDERS:
        before = session.scalar(sa.select(DataSource.id).where(DataSource.name == spec.name))
        ensure_data_source(session, spec)
        if before is None:
            created += 1
    session.commit()
    return created
