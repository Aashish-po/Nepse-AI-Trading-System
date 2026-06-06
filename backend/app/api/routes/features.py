from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.feature import (
    FeatureBatchRequest,
    FeatureBatchResponse,
    FeatureResponse,
    MultiStockFeatureRequest,
    MultiStockFeatureResponse,
)
from backend.app.services.data_quality_gate import DataQualityGate
from backend.app.services.feature import FeatureService

router = APIRouter(prefix="/features", tags=["features"])
DbSession = Annotated[Session, Depends(get_db)]


@router.post("/generate", response_model=FeatureResponse)
def generate_features(symbol: str, date_str: str, db: DbSession) -> FeatureResponse:
    service = FeatureService(gate=DataQualityGate(session=db), session=db)
    try:
        result = service.compute_features(symbol, date_str)
        return FeatureResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/generate-batch", response_model=FeatureBatchResponse)
def generate_features_batch(
    request: FeatureBatchRequest,
    db: DbSession,
) -> FeatureBatchResponse:
    service = FeatureService(gate=DataQualityGate(session=db), session=db)
    try:
        result = service.compute_features_batch(
            request.symbol,
            request.start_date,
            request.end_date,
        )
        return FeatureBatchResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/generate-multi", response_model=MultiStockFeatureResponse)
def generate_features_multi(
    request: MultiStockFeatureRequest,
    db: DbSession,
) -> MultiStockFeatureResponse:
    service = FeatureService(gate=DataQualityGate(session=db), session=db)
    try:
        result = service.compute_features_multi_stock(
            request.symbols,
            request.start_date,
            request.end_date,
        )
        return MultiStockFeatureResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
