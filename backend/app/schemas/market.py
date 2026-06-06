from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


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

    @model_validator(mode="after")
    def validate_price_integrity(self) -> "PriceIngestRequest":
        if self.volume is not None and self.volume < 0:
            raise ValueError("volume must be >= 0")
        values = [v for v in (self.open, self.close) if v is not None]
        if values:
            if self.high is not None and any(self.high < v for v in values):
                raise ValueError("high must be >= open and close")
            if self.low is not None and any(v < self.low for v in values):
                raise ValueError("low must be <= open and close")
        return self


class PriceResponse(BaseModel):
    symbol: str
    date: date
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    volume: int | None
