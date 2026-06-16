from typing import Annotated

import sqlalchemy as sa
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.data_quality import SystemModeHistory
from app.models.user import User
from app.schemas.data_quality import (
    DataQualityReportResponse,
    SymbolQualitySummaryResponse,
    TrustScoreResponse,
)
from app.services.data_quality import DataQualityService
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

router = APIRouter(prefix="/data-quality", tags=["data-quality"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


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
def generate_daily_report(user: CurrentUser, db: DbSession) -> DataQualityReportResponse:
    service = DataQualityService(session=db)
    result = service.generate_daily_report()
    return DataQualityReportResponse(**result)


@router.get("/alerts")
def get_alerts(db: DbSession, report_id: int | None = None) -> list[dict]:
    service = DataQualityService(session=db)
    return service.get_alerts(report_id=report_id)


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: int, user: CurrentUser, db: DbSession) -> dict[str, bool]:
    service = DataQualityService(session=db)
    return {"acknowledged": service.acknowledge_alert(alert_id)}


@router.get("/trends/{symbol}")
def get_trust_trend(symbol: str, db: DbSession, window: int = 30) -> dict:
    service = DataQualityService(session=db)
    return service.get_symbol_trust_trend(symbol, window=window)


@router.get("/freshness/{symbol}/{date_str}")
def check_freshness(symbol: str, date_str: str, db: DbSession) -> dict:
    service = DataQualityService(session=db)
    return service.check_data_freshness(symbol, date_str)


@router.get("/system-mode")
def get_system_mode(db: DbSession) -> dict:
    service = DataQualityService(session=db)
    return service.get_system_mode()


@router.get("/cross-validate/{symbol}/{date_str}")
def cross_validate(symbol: str, date_str: str, db: DbSession, price_field: str = "close") -> dict:
    service = DataQualityService(session=db)
    return service.cross_validate_sources(symbol, date_str, price_field)


@router.get("/source-accuracy/{source_id}")
def get_source_accuracy(source_id: int, db: DbSession) -> dict:
    service = DataQualityService(session=db)
    return {"source_id": source_id, "accuracy_score": service.get_source_accuracy_score(source_id)}


@router.get("/weighted-price/{symbol}/{date_str}")
def get_weighted_price(
    symbol: str, date_str: str, db: DbSession, price_field: str = "close"
) -> dict:
    service = DataQualityService(session=db)
    result = service.calculate_weighted_price(symbol, date_str, price_field)
    return {
        "symbol": symbol.upper(),
        "date": date_str,
        "price_field": price_field,
        "weighted_price": result,
    }


@router.get("/source-drift/{source_id}")
def detect_source_drift(source_id: int, db: DbSession, window: int = 10) -> dict:
    service = DataQualityService(session=db)
    return service.detect_source_drift(source_id, window=window)


@router.get("/mode-history")
def get_mode_history(db: DbSession, limit: int = 100) -> list[dict]:
    modes = list(
        db.scalars(
            sa.select(SystemModeHistory).order_by(SystemModeHistory.timestamp.desc()).limit(limit)
        ).all()
    )
    return [
        {
            "timestamp": m.timestamp.isoformat(),
            "mode": m.mode,
            "unsafe_ratio": m.unsafe_ratio,
            "total_symbols": m.total_symbols,
        }
        for m in modes
    ]


@router.post("/sources/recover-blacklisted")
def recover_blacklisted_sources(user: CurrentUser, db: DbSession, threshold: float = 0.5) -> dict:
    service = DataQualityService(session=db)
    recovered = service.recover_blacklisted_sources(recovery_threshold=threshold)
    return {"recovered_sources": recovered}


@router.post("/trust/apply-decay")
def apply_trust_decay(
    user: CurrentUser, db: DbSession, days_threshold: int = 30, decay_factor: float = 0.95
) -> dict:
    service = DataQualityService(session=db)
    count = service.apply_trust_decay(days_threshold=days_threshold, decay_factor=decay_factor)
    return {"decayed_records": count}


@router.get("/history/{symbol}")
def get_trust_history(symbol: str, db: DbSession, days: int = 30) -> dict:
    service = DataQualityService(session=db)
    return service.get_symbol_trust_trend(symbol, window=days)
