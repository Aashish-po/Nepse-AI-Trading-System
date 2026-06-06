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


class MultiStockFeatureRequest(BaseModel):
    symbols: list[str]
    start_date: str | None = None
    end_date: str | None = None


class MultiStockFeatureResponse(BaseModel):
    feature_version: str
    symbols_requested: int
    symbols_succeeded: int
    total_processed_dates: int
    total_gated_dates: int
    total_inserted_rows: int
    errors: list[dict[str, str]]


class FeatureRetrieveRequest(BaseModel):
    symbol: str
    date: str
    feature_version: str | None = None


class FeatureRetrieveResponse(BaseModel):
    symbol: str
    date: str
    feature_version: str
    trust_score: float | None = None
    trust_version: str | None = None
    features: dict[str, float | None] | None = None
