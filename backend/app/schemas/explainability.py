"""Pydantic schemas for explainability and model governance (Phase 11)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class FeatureContributionSchema(BaseModel):
    feature: str
    value: float
    contribution: float


class GlobalImportanceResponse(BaseModel):
    model_id: str
    model_name: str
    method: str
    importances: list[FeatureContributionSchema]


class ExplainRequest(BaseModel):
    """Request to explain a single prediction by feature values."""

    feature_values: dict[str, Any]
    symbol: str | None = None
    signal_type: str = "ml"
    top_k: int | None = None


class LocalExplanationResponse(BaseModel):
    model_id: str
    method: str
    prediction: int
    base_value: float
    contributions: list[FeatureContributionSchema]
    trade_explanation: dict[str, Any] | None = None


class GovernanceActionRequest(BaseModel):
    """Request body for approval/rejection actions."""

    reviewer: str
    notes: str | None = None


class GovernanceSubmitRequest(BaseModel):
    notes: str | None = None


class GovernanceStatusResponse(BaseModel):
    id: int
    name: str
    version: str
    gate_status: str
    governance_status: str
    production_ready: bool
    reviewer: str | None = None
    reviewed_at: str | None = None
    governance: dict[str, Any]
