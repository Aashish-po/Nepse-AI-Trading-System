"""Tests that external providers are safely opt-in by default (Commit 0).

The critical guarantee: with default settings no provider is "usable", so no
ingestion path will ever make a network call in CI.
"""

from __future__ import annotations

from app.core.config import Settings
from app.services.external.providers import (
    PROVIDERS,
    PROVIDERS_BY_KEY,
    is_enabled,
    provider_status,
)


def _default_settings() -> Settings:
    # Construct in isolation from the developer's real .env values.
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        fred_enabled=False,
        newsapi_enabled=False,
        huggingface_enabled=False,
        marketstack_enabled=False,
        finnhub_enabled=False,
        polygon_enabled=False,
        iexcloud_enabled=False,
        coingecko_enabled=False,
        fixer_enabled=False,
        exchangerate_host_enabled=False,
        contex_dev_enabled=False,
    )


def test_all_providers_disabled_by_default() -> None:
    cfg = _default_settings()
    for spec in PROVIDERS:
        assert is_enabled(spec, cfg) is False, f"{spec.key} should be disabled by default"
    assert cfg.external_api_live_tests is False


def test_enabled_flag_without_key_is_not_usable() -> None:
    # Turning the flag on but leaving the key blank must NOT make it usable.
    cfg = Settings(_env_file=None, fred_enabled=True, fred_api_key="")  # type: ignore[call-arg]
    assert is_enabled(PROVIDERS_BY_KEY["fred"], cfg) is False


def test_enabled_flag_with_key_is_usable() -> None:
    cfg = Settings(_env_file=None, fred_enabled=True, fred_api_key="abc")  # type: ignore[call-arg]
    assert is_enabled(PROVIDERS_BY_KEY["fred"], cfg) is True


def test_keyless_provider_usable_on_flag_alone() -> None:
    cfg = Settings(_env_file=None, coingecko_enabled=True)  # type: ignore[call-arg]
    assert is_enabled(PROVIDERS_BY_KEY["coingecko"], cfg) is True


def test_provider_status_reports_no_secrets() -> None:
    cfg = Settings(_env_file=None, fred_enabled=True, fred_api_key="topsecret")  # type: ignore[call-arg]
    rows = provider_status(cfg)
    serialized = str(rows)
    assert "topsecret" not in serialized
    fred = next(r for r in rows if r["key"] == "fred")
    assert fred["has_key"] is True
    assert fred["usable"] is True
