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
