"""REST API routes for ML training and inference."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Annotated, Any

from app.db.session import get_db
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

# Ensure workspace root is on path for ml/ imports
_workspace_root = Path(__file__).parent.parent.parent.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))  # noqa: E402

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ml"])
DbSession = Annotated[Session, Depends(get_db)]


# Define request/response models here (lightweight, no ml imports)
class DatasetBuildRequest(BaseModel):
    """Request to build a dataset."""

    symbol: str
    feature_version: str = "v4.0.0"


class DatasetBuildResponse(BaseModel):
    """Response with dataset build result."""

    success: bool
    message: str
    bundle_id: str | None = None


class ModelTrainRequest(BaseModel):
    """Request to train a model."""

    symbol: str
    model_name: str = "logistic"


class TrainingResponse(BaseModel):
    """Training result response."""

    success: bool
    symbol: str
    model_name: str
    message: str


class PredictionRequest(BaseModel):
    """Request to make predictions."""

    symbol: str
    model_name: str = "logistic"
    model_version: str = "v1.0.0"
    feature_values: dict[str, Any]


class PredictionResponse(BaseModel):
    """Prediction result."""

    success: bool
    symbol: str
    prediction: int | None = None
    error: str | None = None


# Routes with lazy imports inside handlers


@router.post("/datasets/build", response_model=DatasetBuildResponse)
async def build_dataset(
    request: DatasetBuildRequest,
    session: DbSession,
) -> DatasetBuildResponse:
    """Build a dataset for a given stock symbol."""
    try:
        # Lazy import only when route is called
        from ml.dataset import DatasetBuilder

        builder = DatasetBuilder(session=session, feature_version=request.feature_version)
        bundle = builder.build(request.symbol)
        return DatasetBuildResponse(
            success=True,
            message=f"Dataset built for {request.symbol}",
            bundle_id=str(bundle.symbol),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception(f"Dataset build failed for {request.symbol}")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/models/train", response_model=TrainingResponse)
async def train_model(
    request: ModelTrainRequest,
    session: DbSession,
) -> TrainingResponse:
    """Train ML model for a symbol."""
    try:
        # Lazy imports only when route is called
        from ml.dataset import DatasetBuilder, DatasetBundle
        from ml.training import ModelTrainer

        # Build dataset
        builder = DatasetBuilder(session=session, feature_version="v4.0.0")
        bundle: DatasetBundle = builder.build(request.symbol)

        # Train model
        trainer = ModelTrainer(session=session)
        trainer.train_logistic(bundle, model_name=request.model_name)

        return TrainingResponse(
            success=True,
            symbol=request.symbol,
            model_name=request.model_name,
            message=f"Model trained successfully for {request.symbol}",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception(f"Model training failed for {request.symbol}")
        raise HTTPException(status_code=500, detail="Training failed") from e


@router.post("/models/predict", response_model=PredictionResponse)
async def predict(
    request: PredictionRequest,
) -> PredictionResponse:
    """Make predictions for a symbol using feature values."""
    try:
        # Lazy import only when route is called
        from ml.inference import Predictor

        predictor = Predictor(model_name=request.model_name, model_version=request.model_version)
        # Call predict with correct signature: feature_values: dict[str, Any]
        prediction = predictor.predict(request.feature_values)

        return PredictionResponse(
            success=True,
            symbol=request.symbol,
            prediction=prediction["prediction"],
        )
    except Exception as e:
        logger.exception(f"Prediction failed for {request.symbol}")
        return PredictionResponse(
            success=False,
            symbol=request.symbol,
            error=str(e),
        )


@router.get("/ml/status")
async def ml_status() -> dict[str, str]:
    """Check ML module availability."""
    try:
        import importlib.util

        _ = importlib.util.find_spec("ml.dataset")
        return {"status": "available", "message": "ML modules ready"}
    except ImportError as e:
        return {"status": "unavailable", "message": f"ML modules not loaded: {e}"}
