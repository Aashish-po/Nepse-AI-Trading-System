from pydantic import BaseModel


class IngestionRequest(BaseModel):
    source: str = "primary"
    start_date: str | None = None
    end_date: str | None = None
    dry_run: bool = False
