"""REST API routes for model explainability and governance (Phase 11)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Annotated

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.model_registry import ModelRegistry
from app.models.user import User
from app.schemas.explainability import (
    ExplainRequest,
    FeatureContributionSchema,
    GlobalImportanceResponse,
    GovernanceActionRequest,
    GovernanceStatusResponse,
    GovernanceSubmitRequest,
    LocalExplanationResponse,
)
from app.services.model_governance import GovernanceError, ModelGovernanceService
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

_workspace_root = Path(__file__).parent.parent.parent.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/explain", tags=["explainability"])

DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def _resolve_entry(session: Session, model_id: str) -> ModelRegistry:
    import sqlalchemy as sa

    query = session.query(ModelRegistry)
    entry = None
    if model_id.isdigit():
        entry = query.filter(ModelRegistry.id == int(model_id)).first()
    if entry is None:
        entry = query.filter(
            sa.or_(
                ModelRegistry.version == model_id,
                ModelRegistry.version == f"v{model_id}",
                ModelRegistry.version.contains(model_id),
            )
        ).first()
    if entry is None:
        raise HTTPException(status_code=404, detail="Model not found")
    return entry


@router.get("/models/{model_id}/importance", response_model=GlobalImportanceResponse)
def global_importance(
    model_id: str,
    session: DbSession,
    top_k: int = Query(default=10, ge=1, le=50),
) -> GlobalImportanceResponse:
    """Global feature importance for a trained model."""
    from ml.explainability import ExplainabilityService
    from ml.model_io import safe_load_model

    entry = _resolve_entry(session, model_id)
    try:
        model = safe_load_model(entry.model_artifact_path)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    service = ExplainabilityService()
    result = service.global_importance(model, top_k=top_k)
    return GlobalImportanceResponse(
        model_id=str(entry.id),
        model_name=entry.name,
        method=result.method,
        importances=[FeatureContributionSchema(**c.to_dict()) for c in result.importances],
    )


@router.post("/models/{model_id}/predict", response_model=LocalExplanationResponse)
def explain_prediction(
    model_id: str,
    request: ExplainRequest,
    session: DbSession,
) -> LocalExplanationResponse:
    """Explain a single prediction with per-feature attribution."""
    import numpy as np

    from ml.explainability import ExplainabilityService, explain_trade
    from ml.feature_vector import build_feature_vector
    from ml.model_io import safe_load_model

    entry = _resolve_entry(session, model_id)
    try:
        model = safe_load_model(entry.model_artifact_path)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    vector = build_feature_vector(request.feature_values)
    service = ExplainabilityService()
    explanation = service.explain_prediction(model, vector, top_k=request.top_k)

    confidence = None
    try:
        x = vector.reshape(1, -1)
        if hasattr(model, "predict_proba"):
            confidence = float(np.max(model.predict_proba(x)[0]))
    except Exception:  # pragma: no cover - defensive
        confidence = None

    trade_expl = None
    if request.symbol:
        trade_expl = explain_trade(
            symbol=request.symbol,
            signal_type=request.signal_type,
            prediction=explanation.prediction,
            explanation=explanation,
            confidence=confidence,
        )

    return LocalExplanationResponse(
        model_id=str(entry.id),
        method=explanation.method,
        prediction=explanation.prediction,
        base_value=explanation.base_value,
        contributions=[FeatureContributionSchema(**c.to_dict()) for c in explanation.contributions],
        trade_explanation=trade_expl,
    )


# --------------------------------------------------------------------- governance
gov_router = APIRouter(prefix="/governance", tags=["governance"])


@gov_router.get("/models", response_model=list[GovernanceStatusResponse])
def list_governance(
    session: DbSession,
    state: str | None = Query(default=None),
) -> list[GovernanceStatusResponse]:
    service = ModelGovernanceService(session)
    try:
        return [GovernanceStatusResponse(**s) for s in service.list_by_state(state)]
    except GovernanceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@gov_router.get("/models/{model_id}", response_model=GovernanceStatusResponse)
def governance_status(model_id: str, session: DbSession) -> GovernanceStatusResponse:
    service = ModelGovernanceService(session)
    try:
        return GovernanceStatusResponse(**service.get_status(model_id))
    except GovernanceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@gov_router.post("/models/{model_id}/submit", response_model=GovernanceStatusResponse)
def submit_for_approval(
    model_id: str,
    request: GovernanceSubmitRequest,
    user: CurrentUser,
    session: DbSession,
) -> GovernanceStatusResponse:
    service = ModelGovernanceService(session)
    try:
        return GovernanceStatusResponse(**service.submit_for_approval(model_id, request.notes))
    except GovernanceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@gov_router.post("/models/{model_id}/approve", response_model=GovernanceStatusResponse)
def approve_model(
    model_id: str,
    request: GovernanceActionRequest,
    user: CurrentUser,
    session: DbSession,
) -> GovernanceStatusResponse:
    service = ModelGovernanceService(session)
    try:
        return GovernanceStatusResponse(
            **service.approve(model_id, request.reviewer, request.notes)
        )
    except GovernanceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@gov_router.post("/models/{model_id}/reject", response_model=GovernanceStatusResponse)
def reject_model(
    model_id: str,
    request: GovernanceActionRequest,
    user: CurrentUser,
    session: DbSession,
) -> GovernanceStatusResponse:
    service = ModelGovernanceService(session)
    try:
        return GovernanceStatusResponse(**service.reject(model_id, request.reviewer, request.notes))
    except GovernanceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@gov_router.post("/models/{model_id}/production", response_model=GovernanceStatusResponse)
def mark_production_ready(
    model_id: str,
    request: GovernanceActionRequest,
    user: CurrentUser,
    session: DbSession,
) -> GovernanceStatusResponse:
    service = ModelGovernanceService(session)
    try:
        return GovernanceStatusResponse(**service.mark_production_ready(model_id, request.reviewer))
    except GovernanceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
