from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
        default="change_me_in_local_env",
        validation_alias=AliasChoices("SECRET_KEY", "secret_key"),
    )
    access_token_expire_minutes: int = Field(
        default=60,
        validation_alias=AliasChoices("ACCESS_TOKEN_EXPIRE_MINUTES", "access_token_expire_minutes"),
    )

    database_url: str = Field(
        default="postgresql+psycopg://nepse:change_me@localhost:5432/nepse_ai",
        validation_alias=AliasChoices("DATABASE_URL", "database_url"),
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias=AliasChoices("REDIS_URL", "redis_url"),
    )
    mlflow_tracking_uri: str = Field(
        default="http://localhost:5000",
        validation_alias=AliasChoices("MLFLOW_TRACKING_URI", "mlflow_tracking_uri"),
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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
