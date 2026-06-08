"""Strategy and backtest API routes."""

from typing import Annotated

import sqlalchemy as sa
from app.db.session import get_db
from app.models.backtest import Backtest
from app.schemas.strategy import (
    BacktestCreate,
    BenchmarkCompareRequest,
    StrategyCreate,
    StrategyDetailResponse,
    StrategyResponse,
)
from app.services.backtest import BacktestService
from app.services.benchmark import BenchmarkService
from app.services.strategy import StrategyService
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

router = APIRouter(prefix="/strategies", tags=["strategies"])
DbSession = Annotated[Session, Depends(get_db)]


@router.post("/", response_model=StrategyResponse)
def create_strategy(
    request: StrategyCreate,
    db: DbSession,
) -> StrategyResponse:
    service = StrategyService(session=db)
    strategy = service.create_strategy(
        name=request.name,
        version=request.version,
        config=request.model_dump(),
    )
    return StrategyResponse(
        id=strategy.id,
        name=strategy.name,
        version=strategy.version,
        created_at=strategy.created_at.isoformat() if strategy.created_at else None,
    )


@router.get("/", response_model=list[StrategyResponse])
def list_strategies(
    db: DbSession,
    limit: int = 100,
    offset: int = 0,
) -> list[StrategyResponse]:
    service = StrategyService(session=db)
    strategies = service.list_strategies(limit=limit, offset=offset)
    return [
        StrategyResponse(
            id=s.id,
            name=s.name,
            version=s.version,
            created_at=s.created_at.isoformat() if s.created_at else None,
        )
        for s in strategies
    ]


@router.get("/{strategy_id}", response_model=StrategyDetailResponse)
def get_strategy(
    strategy_id: int,
    db: DbSession,
) -> StrategyDetailResponse:
    service = StrategyService(session=db)
    strategy = service.get_strategy(strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return StrategyDetailResponse(
        id=strategy.id,
        name=strategy.name,
        version=strategy.version,
        description=strategy.config.get("description"),
        config=strategy.config,
        created_at=strategy.created_at.isoformat() if strategy.created_at else None,
    )


@router.post("/backtests", response_model=dict)
def run_backtest(
    request: BacktestCreate,
    db: DbSession,
) -> dict:
    service = BacktestService(session=db)
    result = service.run_backtest(
        strategy_id=request.strategy_id,
        config=request.config.model_dump(),
    )
    return result


@router.get("/backtests/{backtest_id}")
def get_backtest(
    backtest_id: int,
    db: DbSession,
) -> dict:
    backtest = db.scalar(sa.select(Backtest).where(Backtest.id == backtest_id))
    if backtest is None:
        raise HTTPException(status_code=404, detail="Backtest not found")
    return {
        "id": backtest.id,
        "strategy_id": backtest.strategy_id,
        "config": backtest.config,
        "metrics": backtest.metrics,
        "created_at": backtest.created_at.isoformat() if backtest.created_at else None,
    }


@router.post("/benchmarks/compare", response_model=dict)
def compare_with_benchmark(
    request: BenchmarkCompareRequest,
    db: DbSession,
) -> dict:
    service = BenchmarkService(session=db)
    if request.benchmark_type.value == "buy_and_hold":
        if not request.symbol:
            raise HTTPException(status_code=400, detail="Symbol required for buy_and_hold")
        result = service.run_buy_and_hold(
            symbol=request.symbol,
            start_date=request.start_date,
            end_date=request.end_date,
        )
    elif request.benchmark_type.value == "nepse_index":
        result = service.run_nepse_index(
            start_date=request.start_date,
            end_date=request.end_date,
        )
    else:
        raise HTTPException(status_code=400, detail="Unsupported benchmark type")

    return result
