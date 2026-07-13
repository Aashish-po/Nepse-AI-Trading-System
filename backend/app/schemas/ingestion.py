from __future__ import annotations

from pydantic import BaseModel, field_validator


class IngestionRequest(BaseModel):
    source: str = "csv_ingestion"
    start_date: str | None = None
    end_date: str | None = None
    dry_run: bool = False

    @field_validator("source", mode="before")
    @classmethod
    def _normalize_source(cls, value: object) -> str:
        if value is None:
            return "csv_ingestion"
        source = str(value).strip().lower()
        aliases = {
            "csv": "csv_ingestion",
            "csv_ingestion": "csv_ingestion",
            "nepse_data": "csv_ingestion",
            "primary": "csv_ingestion",
            "all": "csv_ingestion",
        }
        return aliases.get(source, source)
