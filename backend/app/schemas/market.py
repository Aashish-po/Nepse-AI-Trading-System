from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class PriceIngestRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    name: str | None = None
    sector: str | None = None
    date: date
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    close: Decimal | None = None
    volume: int | None = None


class PriceResponse(BaseModel):
    symbol: str
    date: date
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    volume: int | None

