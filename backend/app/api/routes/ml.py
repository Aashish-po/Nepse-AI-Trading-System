"""REST API routes for ML training and inference."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from ml.dataset import DatasetBuilder
from ml.evaluation import ModelEvaluator
from ml.inference import Predictor
from ml.labeling import LabelConfig
from ml.training import ModelTrainer

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ml"])
DbSession = Annotated[Session, Depends(get_db)]


class TrainRequest(BaseModel):
    symbol: str
    model_name: str = "logistic"
    model_version: str = "1.0.0"
    feature_version: str = "v4.0.0"
    horizon: int = 5
    up_threshold: float = 0.02
    down_threshold: float = -0.02
    mode: str = "classification"


class TrainResponse(BaseModel):
    symbol: str
    model_name: str
    model_version: str
    model_path: str | None = None
    metrics: dict[str, Any]


class PredictRequest(BaseModel):
    symbol: str
    feature_version: str = "v4.0.0"


class PredictResponse(BaseModel):
    model_name: str
    model_version: str
    prediction: int
    confidence: float
    feature_names: list[str]


@router.post("/train", response_model=TrainResponse)
def train_model(request: TrainRequest, db: DbSession) -> TrainResponse:
    label_config = LabelConfig(
        horizon=request.horizon,
        up_threshold=request.up_threshold,
        down_threshold=request.down_threshold,
    )
    builder = DatasetBuilder(
        session=db, label_config=label_config, feature_version=request.feature_version
    )
    bundle = builder.build(request.symbol)

    trainer = ModelTrainer(session=db, model_version=request.model_version)
    result = trainer.train_logistic(bundle, model_name=request.model_name)

    evaluator = ModelEvaluator(session=db)
    test_metrics = evaluator.evaluate_classification(trainer._model, bundle.X_test, bundle.y_test)
    all_metrics = dict(result.metrics)
    all_metrics.update(test_metrics)

    return TrainResponse(
        symbol=request.symbol,
        model_name=request.model_name,
        model_version=result.model_version,
        model_path=result.model_path,
        metrics=all_metrics,
    )


@router.get("/models")
def list_models(db: DbSession) -> dict[str, Any]:
    from sqlalchemy import select

    from backend.app.models.model_registry import ModelRegistry

    models = db.scalars(select(ModelRegistry).order_by(ModelRegistry.created_at.desc())).all()
    return {
        "models": [
            {
                "id": m.id,
                "name": m.name,
                "version": m.version,
                "metrics": m.metrics,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in models
        ]
    }


@router.get("/predict/{symbol}", response_model=PredictResponse)
def predict(symbol: str, db: DbSession) -> dict[str, Any]:
    from backend.app.services.feature import FeatureService

    fetcher = FeatureService(session=db)
    latest = fetcher.get_features_list(symbol, limit=1, offset=0)
    if not latest["features"]:
        raise HTTPException(status_code=404, detail=f"No features available for {symbol}")
    feature_values = latest["features"][0]["features"]
    if not feature_values:
        raise HTTPException(status_code=404, detail=f"Empty feature set for {symbol}")

    model_name = "logistic"
    model_version = "1.0.0"
    predictor = Predictor(model_name=model_name, model_version=model_version)
    prediction = predictor.predict(feature_values)

    return {
        "model_name": prediction["model_name"],
        "model_version": prediction["model_version"],
        "prediction": prediction["prediction"],
        "confidence": prediction["confidence"],
        "feature_names": prediction["feature_names"],
    }
