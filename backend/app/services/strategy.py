"""Strategy service with registry and versioning support."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from backend.app.db.session import SessionLocal
from backend.app.models.strategy import Strategy

logger = logging.getLogger(__name__)


class StrategyService:
    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    def _get_session(self) -> Session:
        if self._session is not None:
            return self._session
        return SessionLocal()

    def create_strategy(
        self,
        name: str,
        version: str,
        config: dict,
        description: str | None = None,
    ) -> Strategy:
        owns_session = self._session is None
        session = self._get_session()
        try:
            strategy = Strategy(
                name=name,
                version=version,
                config=config,
            )
            session.add(strategy)
            session.commit()
            session.refresh(strategy)
            logger.info(f"Created strategy {name} v{version}")
            return strategy
        finally:
            if owns_session:
                session.close()

    def get_strategy(self, strategy_id: int) -> Strategy | None:
        session = self._get_session()
        owns_session = self._session is None
        try:
            return session.get(Strategy, strategy_id)
        finally:
            if owns_session:
                session.close()

    def get_strategy_by_name_version(
        self, name: str, version: str | None = None
    ) -> Strategy | None:
        session = self._get_session()
        owns_session = self._session is None
        try:
            query = sa.select(Strategy).where(Strategy.name == name)
            if version:
                query = query.where(Strategy.version == version)
            return session.scalar(query)
        finally:
            if owns_session:
                session.close()

    def list_strategies(self, limit: int = 100, offset: int = 0) -> list[Strategy]:
        session = self._get_session()
        owns_session = self._session is None
        try:
            query = (
                sa.select(Strategy)
                .order_by(Strategy.name, Strategy.version)
                .limit(limit)
                .offset(offset)
            )
            return list(session.scalars(query))
        finally:
            if owns_session:
                session.close()

    def evaluate_entry_signal(
        self,
        symbol: str,
        date: str,
        features: Mapping[str, float | None],
        entry_rules: list[dict],
    ) -> bool:
        for rule in entry_rules:
            operator = rule.get("operator", "OR")
            conditions = rule.get("conditions", [rule] if "rule" in rule else [])

            if "rule" in rule:
                conditions = [rule]

            if operator == "AND":
                all_met = True
                for cond in conditions:
                    if not self._evaluate_condition(cond, features):
                        all_met = False
                        break
                if all_met:
                    return True
            else:
                any_met = False
                for cond in conditions:
                    if self._evaluate_condition(cond, features):
                        any_met = True
                        break
                if any_met:
                    return True

        return False

    def _evaluate_condition(
        self,
        rule: dict,
        features: Mapping[str, float | None],
    ) -> bool:
        rule_type = rule.get("rule")
        params = rule.get("params", {})

        if rule_type == "rsi_oversold":
            rsi = features.get("rsi_14")
            if rsi is not None and rsi < params.get("threshold", 30):
                return True
        elif rule_type == "rsi_overbought":
            rsi = features.get("rsi_14")
            if rsi is not None and rsi > params.get("threshold", 70):
                return True
        elif rule_type == "sma_cross_up":
            sma_20 = features.get("sma_20")
            sma_50 = features.get("sma_50")
            if sma_20 is not None and sma_50 is not None and sma_20 > sma_50:
                return True
        elif rule_type == "sma_cross_down":
            sma_20 = features.get("sma_20")
            sma_50 = features.get("sma_50")
            close = features.get("close")
            if sma_20 is not None and sma_50 is not None and close is not None and sma_20 < sma_50:
                return True
        elif rule_type == "macd_cross_up":
            macd = features.get("macd")
            signal = features.get("macd_signal")
            if macd is not None and signal is not None and macd > signal:
                return True
        elif rule_type == "breakout_high":
            close = features.get("close")
            high_threshold = params.get("threshold", 105.0)
            if close is not None and close > high_threshold:
                return True

        return False

    def evaluate_exit_signal(
        self,
        symbol: str,
        date: str,
        features: Mapping[str, float | None],
        exit_rules: list[dict],
        position: Any,
    ) -> bool:
        for rule in exit_rules:
            rule_type = rule.get("rule")
            params = rule.get("params", {})

            if rule_type == "rsi_exit_long":
                rsi = features.get("rsi_14")
                if rsi is not None and rsi > params.get("threshold", 70):
                    return True
            elif rule_type == "take_profit":
                target = params.get("target", 0.1)
                if position:
                    current_price = features.get("close")
                    if current_price and position.entry_price:
                        return_pct = (float(current_price) - float(position.entry_price)) / float(
                            position.entry_price
                        )
                        if return_pct >= target:
                            return True
            elif rule_type == "stop_loss":
                stop = params.get("stop", 0.05)
                if position:
                    current_price = features.get("close")
                    if current_price and position.entry_price:
                        return_pct = (float(current_price) - float(position.entry_price)) / float(
                            position.entry_price
                        )
                        if return_pct <= -stop:
                            return True
            elif rule_type == "trailing_stop":
                trail_pct = params.get("trail_pct", 0.10)
                if position and hasattr(position, "trailing_high"):
                    close = features.get("close")
                    if close:
                        if float(close) > position.trailing_high:
                            position.trailing_high = float(close)
                        trail_level = position.trailing_high * (1 - trail_pct)
                        if float(close) < trail_level:
                            return True

        return False

    def check_risk_rules(
        self,
        portfolio: dict[str, Any],
        risk_rules: list[dict],
        symbol: str,
    ) -> dict[str, Any]:
        allowed_qty = (
            portfolio.get("cash", 0) / portfolio.get("price", 1) if portfolio.get("price") else 0
        )

        for rule in risk_rules:
            rule_type = rule.get("rule")
            params = rule.get("params", {})

            if rule_type == "max_position_size":
                max_pct = params.get("max_pct", 0.1)
                max_shares = int(portfolio.get("cash", 0) * max_pct / portfolio.get("price", 1))
                allowed_qty = min(allowed_qty, max_shares)
            elif rule_type == "single_stock_exposure":
                max_pct = params.get("max_pct", 0.2)
                max_value = portfolio.get("cash", 0) * max_pct
                max_shares = int(max_value / portfolio.get("price", 1))
                allowed_qty = min(allowed_qty, max_shares)

        return {"max_quantity": max(0, int(allowed_qty))}
