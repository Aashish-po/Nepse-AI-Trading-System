from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET_KEY = "change_me_in_local_env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["local", "test", "dev", "prod"] = Field(
        default="local",
        validation_alias=AliasChoices("APP_ENV", "app_env"),
    )
    app_name: str = Field(
        default="NEPSE AI Trading Research Platform",
        validation_alias=AliasChoices("APP_NAME", "app_name"),
    )
    app_version: str = Field(
        default="0.1.0",
        validation_alias=AliasChoices("APP_VERSION", "app_version"),
    )

    secret_key: str = Field(
        default=DEFAULT_SECRET_KEY,
        validation_alias=AliasChoices("SECRET_KEY", "secret_key"),
    )
    access_token_expire_minutes: int = Field(
        default=60,
        validation_alias=AliasChoices("ACCESS_TOKEN_EXPIRE_MINUTES", "access_token_expire_minutes"),
    )

    database_url: str = Field(
        default="sqlite:///./nepse_ai.db",
        validation_alias=AliasChoices("DATABASE_URL", "database_url"),
    )
    database_pool_size: int = Field(
        default=10,
        validation_alias=AliasChoices("DATABASE_POOL_SIZE", "database_pool_size"),
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias=AliasChoices("REDIS_URL", "redis_url"),
    )
    mlflow_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("MLFLOW_ENABLED", "mlflow_enabled"),
    )
    mlflow_tracking_uri: str = Field(
        default="file:./mlruns",
        validation_alias=AliasChoices("MLFLOW_TRACKING_URI", "mlflow_tracking_uri"),
    )
    mlflow_experiment_prefix: str = Field(
        default="",
        validation_alias=AliasChoices("MLFLOW_EXPERIMENT_PREFIX", "mlflow_experiment_prefix"),
    )

    nepse_primary_data_source_url: str = Field(
        default="",
        validation_alias=AliasChoices(
            "NEPSE_PRIMARY_DATA_SOURCE_URL",
            "nepse_primary_data_source_url",
        ),
    )
    nepse_backup_data_source_url: str = Field(
        default="",
        validation_alias=AliasChoices(
            "NEPSE_BACKUP_DATA_SOURCE_URL",
            "nepse_backup_data_source_url",
        ),
    )
    data_trust_score_minimum: float = Field(
        default=0.90,
        validation_alias=AliasChoices("DATA_TRUST_SCORE_MINIMUM", "data_trust_score_minimum"),
    )

    calendarific_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("CALENDARIFIC_API_KEY", "calendarific_api_key"),
    )
    calendarific_country: str = Field(
        default="NP",
        validation_alias=AliasChoices("CALENDARIFIC_COUNTRY", "calendarific_country"),
    )
    # When True, only national/public holidays close the market (Calendarific
    # returns many observance/season entries that NEPSE does not close for).
    calendarific_national_only: bool = Field(
        default=False,
        validation_alias=AliasChoices("CALENDARIFIC_NATIONAL_ONLY", "calendarific_national_only"),
    )

    # External research-data providers (advisory only; never trigger live trading)
    # All providers are OPT-IN. Leaving keys blank and *_ENABLED=false means the
    # system makes ZERO external API calls. Enable a provider only after adding its
    # key. Do NOT commit real keys.

    # Set true ONLY to run opt-in live integration tests against real providers.
    external_api_live_tests: bool = Field(
        default=False,
        validation_alias=AliasChoices("EXTERNAL_API_LIVE_TESTS", "external_api_live_tests"),
    )

    # FRED — macro series (rates, inflation, unemployment, GDP)
    fred_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("FRED_ENABLED", "fred_enabled"),
    )
    fred_base_url: str = Field(
        default="https://api.stlouisfed.org",
        validation_alias=AliasChoices("FRED_BASE_URL", "fred_base_url"),
    )
    fred_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("FRED_API_KEY", "fred_api_key"),
    )
    fred_rate_limit_per_minute: int = Field(
        default=60,
        validation_alias=AliasChoices("FRED_RATE_LIMIT_PER_MINUTE", "fred_rate_limit_per_minute"),
    )
    fred_default_series: str = Field(
        default="DGS10,DGS2,DFF,CPIAUCSL,UNRATE,GDP",
        validation_alias=AliasChoices("FRED_DEFAULT_SERIES", "fred_default_series"),
    )

    # NewsAPI — financial headlines for sentiment
    newsapi_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("NEWSAPI_ENABLED", "newsapi_enabled"),
    )
    newsapi_base_url: str = Field(
        default="https://newsapi.org",
        validation_alias=AliasChoices("NEWSAPI_BASE_URL", "newsapi_base_url"),
    )
    newsapi_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("NEWSAPI_API_KEY", "newsapi_api_key"),
    )
    newsapi_rate_limit_per_minute: int = Field(
        default=30,
        validation_alias=AliasChoices(
            "NEWSAPI_RATE_LIMIT_PER_MINUTE", "newsapi_rate_limit_per_minute"
        ),
    )

    # Hugging Face — optional hosted NLP enrichment
    huggingface_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("HUGGINGFACE_ENABLED", "huggingface_enabled"),
    )
    huggingface_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("HUGGINGFACE_API_KEY", "huggingface_api_key"),
    )
    huggingface_base_url: str = Field(
        default="https://api-inference.huggingface.co",
        validation_alias=AliasChoices("HUGGINGFACE_BASE_URL", "huggingface_base_url"),
    )
    huggingface_model: str = Field(
        default="cardiffnlp/twitter-xlm-roberta-base-sentiment",
        validation_alias=AliasChoices("HUGGINGFACE_MODEL", "huggingface_model"),
    )
    huggingface_rate_limit_per_minute: int = Field(
        default=30,
        validation_alias=AliasChoices(
            "HUGGINGFACE_RATE_LIMIT_PER_MINUTE", "huggingface_rate_limit_per_minute"
        ),
    )

    # Marketstack — global OHLCV / benchmark context
    marketstack_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("MARKETSTACK_ENABLED", "marketstack_enabled"),
    )
    marketstack_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("MARKETSTACK_API_KEY", "marketstack_api_key"),
    )
    marketstack_base_url: str = Field(
        default="https://api.marketstack.com",
        validation_alias=AliasChoices("MARKETSTACK_BASE_URL", "marketstack_base_url"),
    )
    marketstack_rate_limit_per_minute: int = Field(
        default=30,
        validation_alias=AliasChoices(
            "MARKETSTACK_RATE_LIMIT_PER_MINUTE", "marketstack_rate_limit_per_minute"
        ),
    )

    # Finnhub — candles, fundamentals, earnings
    finnhub_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("FINNHUB_ENABLED", "finnhub_enabled"),
    )
    finnhub_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("FINNHUB_API_KEY", "finnhub_api_key"),
    )
    finnhub_base_url: str = Field(
        default="https://finnhub.io",
        validation_alias=AliasChoices("FINNHUB_BASE_URL", "finnhub_base_url"),
    )
    finnhub_rate_limit_per_minute: int = Field(
        default=30,
        validation_alias=AliasChoices(
            "FINNHUB_RATE_LIMIT_PER_MINUTE", "finnhub_rate_limit_per_minute"
        ),
    )

    # Optional scale providers (disabled by default)
    polygon_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("POLYGON_ENABLED", "polygon_enabled"),
    )
    polygon_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("POLYGON_API_KEY", "polygon_api_key"),
    )

    iexcloud_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("IEXCLOUD_ENABLED", "iexcloud_enabled"),
    )
    iexcloud_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("IEXCLOUD_API_KEY", "iexcloud_api_key"),
    )

    coingecko_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("COINGECKO_ENABLED", "coingecko_enabled"),
    )

    fixer_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("FIXER_ENABLED", "fixer_enabled"),
    )
    fixer_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("FIXER_API_KEY", "fixer_api_key"),
    )

    exchangerate_host_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("EXCHANGERATE_HOST_ENABLED", "exchangerate_host_enabled"),
    )

    @model_validator(mode="after")
    def _require_secret_key_outside_local(self) -> Settings:
        # A predictable secret lets anyone forge JWTs. Allow the placeholder only
        # for local/test work; refuse to boot a dev/prod app without a real key.
        if self.app_env in ("dev", "prod") and self.secret_key == DEFAULT_SECRET_KEY:
            raise ValueError(
                "SECRET_KEY must be set to a non-default value when APP_ENV is "
                f"'{self.app_env}'."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
