from pydantic import BaseModel


class TrustScoreResponse(BaseModel):
    symbol: str
    date: str
    trust_score: float
    status: str
    safe: bool
    details: dict
    components: dict


class SymbolQualitySummaryResponse(BaseModel):
    symbol: str
    total_records: int
    avg_trust_score: float
    unsafe_days: int
    warning_days: int
    excellent_days: int
    unsafe_pct: float
    common_issues: list[tuple[str, int]]


class DataQualityReportResponse(BaseModel):
    report_id: int | None = None
    report_date: str
    total_symbols: int
    symbols_passed: int
    symbols_failed: int
    avg_trust_score: float | None
    total_rejected_records: int
    total_missing_dates: int
    total_volume_anomalies: int


class DataQualityAlertResponse(BaseModel):
    id: int
    report_id: int
    symbol: str
    date: str
    severity: str
    message: str
    acknowledged: bool
    created_at: str
