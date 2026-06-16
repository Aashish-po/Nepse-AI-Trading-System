"""REST API routes for ML training and inference."""

from __future__ import annotations

import logging
import sys

# Ensure workspace root is on path for ml/ imports
from pathlib import Path
from typing import Annotated, Any

import numpy as np
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

_workspace_root = Path(__file__).parent.parent.parent.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))  # noqa: E402

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ml"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]

# Late imports for ml package (after path setup)
from ml.feature_vector import build_feature_vector  # noqa: E402
from ml.model_io import safe_load_model  # noqa: E402


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
    model_id: str | None = None
    metrics: dict[str, Any] | None = None
    promotion_status: str | None = None


class ListModelsResponse(BaseModel):
    """Response for listing models."""

    total: int
    models: list[dict[str, Any]]


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
    user: CurrentUser,
    session: Session = Depends(get_db),
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
    user: CurrentUser,
    session: Session = Depends(get_db),
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
    user: CurrentUser,
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


class TrainModelRequest(BaseModel):
    """Request to train a model with Phase 7 parameters."""

    model_name: str = "logistic"
    symbols: list[str] = ["NABIL"]
    start_date: str | None = None
    end_date: str | None = None
    validation_method: str = "single_split"
    random_state: int = 42


@router.post("/ml/models/train", response_model=TrainingResponse)
async def train_model_phase7(
    request: TrainModelRequest,
    user: CurrentUser,
    session: DbSession,
) -> TrainingResponse:
    """Train a baseline ML model with Phase 7 enhancements."""
    try:
        from datetime import date as date_type

        from ml.dataset import DatasetBuilder
        from ml.training import ModelTrainer

        builder = DatasetBuilder(session=session, feature_version="v4.0.0")

        if request.validation_method == "walk_forward":
            start_dt = (
                date_type.fromisoformat(request.start_date)
                if request.start_date
                else date_type(2022, 1, 1)
            )
            end_dt = (
                date_type.fromisoformat(request.end_date) if request.end_date else date_type.today()
            )
            trainer = ModelTrainer(session=session)
            result = trainer.train_walk_forward(
                builder=builder,
                symbols=request.symbols,
                start_date=start_dt,
                end_date=end_dt,
                model_name=request.model_name,
                random_state=request.random_state,
            )
            return TrainingResponse(
                success=True,
                symbol=request.symbols[0] if request.symbols else "MULTI",
                model_name=request.model_name,
                message=f"Walk-forward training completed: {result.get('n_folds', 0)} folds",
                model_id=result.get("model_id"),
                metrics=result.get("metrics"),
                promotion_status=result.get("promotion_status"),
            )
        else:
            bundle = builder.build(request.symbols[0])
            trainer = ModelTrainer(session=session)
            result = trainer.train_baseline(
                bundle, model_name=request.model_name, random_state=request.random_state
            )
            return TrainingResponse(
                success=True,
                symbol=request.symbols[0],
                model_name=request.model_name,
                message="Model trained successfully",
                model_id=result.get("model_id"),
                metrics=result.get("metrics"),
                promotion_status=result.get("promotion_status"),
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("Model training failed")
        raise HTTPException(status_code=500, detail="Training failed") from e


@router.get("/ml/models", response_model=ListModelsResponse)
async def list_models(session: DbSession, status: str | None = None) -> ListModelsResponse:
    """List trained models, optionally filtered by status."""
    try:
        from app.models.model_registry import ModelRegistry

        query = session.query(ModelRegistry)
        if status:
            query = query.filter(ModelRegistry.params.contains({"status": status}))

        models = query.order_by(ModelRegistry.created_at.desc()).all()

        model_list = [
            {
                "id": m.version.split("_")[-1] if "_" in m.version else m.id,
                "name": m.name,
                "version": m.version,
                "status": m.params.get("status", "unknown") if m.params else "unknown",
                "metrics": m.metrics,
                "created_at": m.created_at.isoformat(),
            }
            for m in models
        ]

        return ListModelsResponse(total=len(model_list), models=model_list)
    except Exception as e:
        logger.exception("Failed to list models")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.post("/ml/models/{model_id}/predict", response_model=PredictionResponse)
async def predict_by_id(
    model_id: str,
    request: PredictionRequest,
    user: CurrentUser,
    session: DbSession,
) -> PredictionResponse:
    """Get prediction from a trained model by ID."""
    try:
        import sqlalchemy
        from app.models.model_registry import ModelRegistry

        model_prefix = model_id[:8] if len(model_id) >= 8 else model_id
        entry = (
            session.query(ModelRegistry)
            .filter(
                sqlalchemy.or_(
                    ModelRegistry.name == model_prefix,
                    ModelRegistry.params["model_id"].astext.contains(model_id),
                )
            )
            .first()
        )
        if not entry:
            entry = (
                session.query(ModelRegistry)
                .filter(
                    sqlalchemy.or_(
                        ModelRegistry.id == model_id,
                        ModelRegistry.version.contains(model_id),
                        ModelRegistry.params["model_id"].astext.contains(model_id),
                    )
                )
                .first()
            )

        if not entry:
            raise HTTPException(status_code=404, detail="Model not found")

        model = safe_load_model(entry.model_artifact_path)
        vector = build_feature_vector(request.feature_values)
        X = vector.reshape(1, -1)
        prediction = int(model.predict(X)[0])
        _confidence = (
            float(np.max(model.predict_proba(X)[0])) if hasattr(model, "predict_proba") else 0.5
        )

        return PredictionResponse(
            success=True,
            symbol=request.symbol,
            prediction=prediction,
            error=None,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Prediction failed")
        return PredictionResponse(success=False, symbol=request.symbol, error=str(e))


@router.post("/ml/lstm/train")
async def train_lstm(
    symbol: str, db: Session = Depends(get_db), user: dict = Depends(get_current_user)
):
    """Train LSTM on symbol's historical features"""
    # ... implementation would go here, but is omitted for brevity and focus on testable components
