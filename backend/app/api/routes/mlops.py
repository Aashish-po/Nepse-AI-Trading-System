"""REST API routes for meta-learning and MLOps (Phase 12)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Annotated, Any

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services.mlops import MLOpsService
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

_workspace_root = Path(__file__).parent.parent.parent.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/mlops", tags=["mlops"])

DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


class ChampionResponse(BaseModel):
    metric: str
    champion: dict[str, Any] | None


class RankResponse(BaseModel):
    metric: str
    models: list[dict[str, Any]]


class RetrainAssessmentResponse(BaseModel):
    model_version: str
    should_retrain: bool
    reasons: list[str]
    triggers: dict[str, Any]
    champion: dict[str, Any] | None


class RetrainRequest(BaseModel):
    symbols: list[str] = ["NABIL"]
    model_name: str = "logistic"
    random_state: int = 42


class RetrainResponse(BaseModel):
    success: bool
    model_id: str | None = None
    promotion_status: str | None = None
    metrics: dict[str, Any] | None = None


class EvolveRequest(BaseModel):
    """Hyperparameter evolution over a synthetic/declared search space.

    ``space`` maps param name -> list of categorical values OR [low, high] range.
    ``target`` is an optional dict of target values used by the demo fitness
    (negative squared distance), enabling deterministic, dependency-free search.
    """

    space: dict[str, Any]
    target: dict[str, float] | None = None
    population_size: int = 8
    generations: int = 5
    seed: int = 42


class EvolveResponse(BaseModel):
    best_params: dict[str, Any]
    best_score: float
    history: list[dict[str, Any]]


@router.get("/champion", response_model=ChampionResponse)
def get_champion(
    session: DbSession,
    name: str | None = Query(default=None),
    metric: str = Query(default="sharpe_ratio"),
) -> ChampionResponse:
    """Select the best registered model by a metric."""
    service = MLOpsService(session)
    return ChampionResponse(metric=metric, champion=service.select_champion(name, metric))


@router.get("/rank", response_model=RankResponse)
def rank_models(
    session: DbSession,
    name: str | None = Query(default=None),
    metric: str = Query(default="sharpe_ratio"),
) -> RankResponse:
    """Rank registered models by a metric (best first)."""
    service = MLOpsService(session)
    return RankResponse(metric=metric, models=service.rank_models(name, metric))


@router.get("/models/{model_id}/retrain-assessment", response_model=RetrainAssessmentResponse)
def assess_retraining(
    model_id: str,
    session: DbSession,
    metric: str = Query(default="sharpe_ratio"),
) -> RetrainAssessmentResponse:
    """Assess whether a model should be retrained based on performance and age."""
    service = MLOpsService(session)
    try:
        result = service.assess_retraining(model_id, metric=metric)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RetrainAssessmentResponse(**result)


@router.post("/retrain", response_model=RetrainResponse)
def retrain(
    request: RetrainRequest,
    user: CurrentUser,
    session: DbSession,
) -> RetrainResponse:
    """Trigger a retraining run."""
    service = MLOpsService(session)
    try:
        result = service.retrain(
            symbols=request.symbols,
            model_name=request.model_name,
            random_state=request.random_state,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Retraining failed")
        raise HTTPException(status_code=500, detail="Retraining failed") from exc
    return RetrainResponse(success=True, **result)


@router.post("/evolve", response_model=EvolveResponse)
def evolve_hyperparameters(
    request: EvolveRequest,
    user: CurrentUser,
) -> EvolveResponse:
    """Run evolutionary hyperparameter search against a declarative fitness target."""
    from ml.meta_learning import HyperparameterEvolution, HyperparamSpace

    space = HyperparamSpace(params=request.space)

    target = request.target or {}

    def fitness(genome: dict[str, Any]) -> float:
        # Deterministic demo fitness: maximize negative squared distance to target
        # for numeric params present in both genome and target.
        score = 0.0
        for key, target_val in target.items():
            if key in genome and isinstance(genome[key], int | float):
                score -= (float(genome[key]) - float(target_val)) ** 2
        return score

    evolution = HyperparameterEvolution(
        space=space,
        population_size=request.population_size,
        generations=request.generations,
        seed=request.seed,
    )
    result = evolution.evolve(fitness)
    return EvolveResponse(
        best_params=result.best_params,
        best_score=result.best_score,
        history=result.history,
    )
