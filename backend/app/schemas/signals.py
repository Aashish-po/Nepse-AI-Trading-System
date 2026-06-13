from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ProviderQuotaResponse(BaseModel):
    provider: str
    date: str
    request_count: int
    signal_count: int
    updated_count: int
    success_count: int
    failure_count: int
    skipped_count: int
    token_count: int
    cost: float
    metadata: dict[str, Any] | None = None


class ProviderQuotaSummaryResponse(BaseModel):
    date: str
    providers: list[ProviderQuotaResponse]
    total_request_count: int
    total_signal_count: int
    total_success_count: int
    total_failure_count: int
    total_skipped_count: int
    total_token_count: int
    total_cost: float
