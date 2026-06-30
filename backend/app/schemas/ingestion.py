from __future__ import annotations

from pydantic import BaseModel


class IngestionRequest(BaseModel):
    source: str = "csv_ingestion"
    start_date: str | None = None
    end_date: str | None = None
    dry_run: bool = False
