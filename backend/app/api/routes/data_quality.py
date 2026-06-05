from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.data_quality import (
    DataQualityReportResponse,
    SymbolQualitySummaryResponse,
    TrustScoreResponse,
)
from backend.app.services.data_quality import DataQualityService

router = APIRouter(prefix="/data-quality", tags=["data-quality"])
DbSession = Annotated[Session, Depends(get_db)]


@router.get("/trust/{symbol}/{date_str}", response_model=TrustScoreResponse)
def get_trust_score(symbol: str, date_str: str, db: DbSession) -> TrustScoreResponse:
    service = DataQualityService(session=db)
    result = service.evaluate_symbol_date(symbol, date_str)
    return TrustScoreResponse(
        symbol=symbol.upper(),
        date=date_str,
        trust_score=result["trust_score"],
        status=result.get("status", "unsafe"),
        safe=result["safe"],
        details=result.get("details", {}),
        components=result.get("components", {}),
    )


@router.get("/safe/{symbol}/{date_str}")
def is_data_safe(symbol: str, date_str: str, db: DbSession) -> dict[str, bool]:
    service = DataQualityService(session=db)
    return {"safe": service.is_data_safe(symbol, date_str)}


@router.get("/summary/{symbol}", response_model=SymbolQualitySummaryResponse)
def get_symbol_summary(symbol: str, db: DbSession) -> SymbolQualitySummaryResponse:
    service = DataQualityService(session=db)
    result = service.get_symbol_quality_summary(symbol)
    return SymbolQualitySummaryResponse(**result)


@router.post("/reports/daily", response_model=DataQualityReportResponse)
def generate_daily_report(db: DbSession) -> DataQualityReportResponse:
    service = DataQualityService(session=db)
    result = service.generate_daily_report()
    return DataQualityReportResponse(**result)
