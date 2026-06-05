from pydantic import BaseModel


class FeatureResponse(BaseModel):
    symbol: str
    date: str
    feature_version: str
    features: dict[str, float | None]


class FeatureBatchRequest(BaseModel):
    symbol: str
    start_date: str | None = None
    end_date: str | None = None


class FeatureBatchResponse(BaseModel):
    symbol: str
    feature_version: str
    total_dates: int
    gated_dates: int
    processed_dates: int
    inserted_rows: int
    features_computed: list[str]