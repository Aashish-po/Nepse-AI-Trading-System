from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["local", "test", "dev", "prod"] = "local"
    app_name: str = "NEPSE AI Trading Research Platform"
    app_version: str = "0.1.0"

    secret_key: str = Field(default="change_me_in_local_env")
    access_token_expire_minutes: int = 60

    database_url: str = "postgresql+psycopg://nepse:change_me@localhost:5432/nepse_ai"
    redis_url: str = "redis://localhost:6379/0"
    mlflow_tracking_uri: str = "http://localhost:5000"

    nepse_primary_data_source_url: str = ""
    nepse_backup_data_source_url: str = ""
    data_trust_score_minimum: float = 0.90


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

