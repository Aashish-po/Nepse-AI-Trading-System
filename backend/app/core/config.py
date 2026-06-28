from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET_KEY = "change_me_in_local_env"


class Settings(BaseSettings):
    # case_sensitive defaults to False, so env vars map to field names regardless
    # of case (APP_ENV -> app_env). Only providers whose env var name differs from
    # the field name need an explicit validation_alias (see contex_dev_* below).
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["local", "test", "dev", "prod"] = "local"
    app_name: str = "NEPSE AI Trading Research Platform"
    app_version: str = "0.1.0"

    secret_key: str = DEFAULT_SECRET_KEY
    access_token_expire_minutes: int = 60

    database_url: str = "sqlite:///./nepse_ai.db"
    database_pool_size: int = 10
    database_connect_timeout: int = Field(
        default=2,
        description="Seconds to wait for a (non-SQLite) DB connection before failing fast.",
    )
    redis_url: str = "redis://localhost:6379/0"
    mlflow_enabled: bool = True
    mlflow_tracking_uri: str = "file:./mlruns"
    mlflow_experiment_prefix: str = ""

    nepse_primary_data_source_url: str = ""
    nepse_backup_data_source_url: str = ""
    data_trust_score_minimum: float = 0.90

    calendarific_api_key: str = ""
    calendarific_country: str = "NP"
    # When True, only national/public holidays close the market (Calendarific
    # returns many observance/season entries that NEPSE does not close for).
    calendarific_national_only: bool = False

    # External research-data providers (advisory only; never trigger live trading)
    # All providers are OPT-IN. Leaving keys blank and *_ENABLED=false means the
    # system makes ZERO external API calls. Enable a provider only after adding its
    # key. Do NOT commit real keys.

    # Set true ONLY to run opt-in live integration tests against real providers.
    external_api_live_tests: bool = False

    # FRED — macro series (rates, inflation, unemployment, GDP)
    fred_enabled: bool = False
    fred_base_url: str = "https://api.stlouisfed.org"
    fred_api_key: str = ""
    fred_rate_limit_per_minute: int = 60
    fred_default_series: str = "DGS10,DGS2,DFF,CPIAUCSL,UNRATE,GDP"

    # NewsAPI — financial headlines for sentiment
    newsapi_enabled: bool = False
    newsapi_base_url: str = "https://newsapi.org"
    newsapi_api_key: str = ""
    newsapi_rate_limit_per_minute: int = 30

    # Hugging Face — optional hosted NLP enrichment
    huggingface_enabled: bool = False
    huggingface_api_key: str = ""
    huggingface_base_url: str = "https://api-inference.huggingface.co"
    huggingface_model: str = "cardiffnlp/twitter-xlm-roberta-base-sentiment"
    huggingface_rate_limit_per_minute: int = 30

    # Marketstack — global OHLCV / benchmark context
    marketstack_enabled: bool = False
    marketstack_api_key: str = ""
    marketstack_base_url: str = "https://api.marketstack.com"
    marketstack_rate_limit_per_minute: int = 30

    # Finnhub — candles, fundamentals, earnings
    finnhub_enabled: bool = False
    finnhub_api_key: str = ""
    finnhub_base_url: str = "https://finnhub.io"
    finnhub_rate_limit_per_minute: int = 30

    # Context.dev — enriched market context / entity extraction.
    # Key/base-url env vars use provider-specific names that differ from the field
    # name, so these two keep an explicit validation_alias.
    contex_dev_enabled: bool = False
    contex_dev_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("CONTEX.DEV", "contex_dev_api_key"),
    )
    contex_dev_base_url: str = Field(
        default="https://api.context.dev/",
        validation_alias=AliasChoices("CONTEX_BASE_URL", "contex_dev_base_url"),
    )

    @model_validator(mode="after")
    def _require_secret_key_outside_local(self) -> Settings:
        # A predictable secret lets anyone forge JWTs. Allow the placeholder only
        # for local/test work; refuse to boot a dev/prod app without a real key.
        if self.app_env in ("dev", "prod") and self.secret_key == DEFAULT_SECRET_KEY:
            raise ValueError(
                f"SECRET_KEY must be set to a non-default value when APP_ENV is '{self.app_env}'."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
