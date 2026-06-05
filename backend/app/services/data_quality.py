from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from backend.app.db.session import SessionLocal
from backend.app.models.data_quality import DataQualityReport, DataTrust, HolidayCalendar
from backend.app.models.data_source import IngestionLog
from backend.app.models.price import Price
from backend.app.models.stock import Stock


class DataQualityService:
    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    def _get_session(self) -> Session:
        if self._session is not None:
            return self._session
        return SessionLocal()

    def evaluate_symbol_date(
        self,
        symbol: str,
        date_str: str,
        session: Session | None = None,
    ) -> dict[str, Any]:
        owns_session = session is None
        if owns_session:
            session = self._get_session()
        try:
            stock = session.scalar(sa.select(Stock).where(Stock.symbol == symbol.upper()))
            if stock is None:
                return {
                    "trust_score": 0.0,
                    "status": "unsafe",
                    "safe": False,
                    "reason": "stock_not_found",
                    "components": {},
                }

            price = session.scalar(
                sa.select(Price).where(
                    Price.stock_id == stock.id,
                    Price.date == date_str,
                )
            )
            if price is None:
                return {
                    "trust_score": 0.0,
                    "status": "unsafe",
                    "safe": False,
                    "reason": "no_price_data",
                    "components": {},
                }

            trust_score, details, components = self._compute_trust_score(session, stock.id, price)
            status = self._classify_status(trust_score)
            is_safe = trust_score >= 0.7

            trust = DataTrust(
                stock_id=stock.id,
                date=price.date,
                trust_score=trust_score,
                completeness_score=details.get("completeness_score"),
                volume_anomaly_detected=details.get("volume_anomaly"),
                missing_dates_count=details.get("missing_dates_count"),
                rejected_count=details.get("rejected_count"),
                details=json.dumps(details),
            )
            session.add(trust)
            session.commit()

            return {
                "trust_score": trust_score,
                "status": status,
                "safe": is_safe,
                "details": details,
                "components": components,
            }
        finally:
            if owns_session and session is not self._session:
                session.close()

    def generate_daily_report(self, report_date: str | None = None) -> dict[str, Any]:
        session = self._get_session()
        owns_session = self._session is None
        try:
            target_date = (
                datetime.strptime(report_date, "%Y-%m-%d").date()
                if report_date
                else datetime.now(UTC).date()
            )
            stocks = list(session.scalars(sa.select(Stock)).all())
            total_symbols = len(stocks)
            passed = 0
            failed = 0
            total_rejected = 0
            total_missing = 0
            total_anomalies = 0
            trust_scores: list[float] = []

            for stock in stocks:
                result = self.evaluate_symbol_date(
                    stock.symbol, target_date.isoformat(), session=session
                )
                if result.get("safe"):
                    passed += 1
                else:
                    failed += 1
                d = result.get("details", {})
                trust_scores.append(result.get("trust_score", 0.0))
                total_rejected += d.get("rejected_count", 0) or 0
                total_missing += d.get("missing_dates_count", 0) or 0
                if d.get("volume_anomaly"):
                    total_anomalies += 1

            avg_trust = sum(trust_scores) / len(trust_scores) if trust_scores else 0.0
            report = DataQualityReport(
                report_date=target_date,
                total_symbols=total_symbols,
                symbols_passed=passed,
                symbols_failed=failed,
                avg_trust_score=avg_trust,
                total_rejected_records=total_rejected,
                total_missing_dates=total_missing,
                total_volume_anomalies=total_anomalies,
                created_at=datetime.now(UTC),
                details=json.dumps(
                    {
                        "generated_at": datetime.now(UTC).isoformat(),
                        "threshold": 0.7,
                        "stocks": [s.symbol for s in stocks],
                    }
                ),
            )
            session.add(report)
            session.commit()

            return {
                "report_date": target_date.isoformat(),
                "total_symbols": total_symbols,
                "symbols_passed": passed,
                "symbols_failed": failed,
                "avg_trust_score": avg_trust,
                "total_rejected_records": total_rejected,
                "total_missing_dates": total_missing,
                "total_volume_anomalies": total_anomalies,
            }
        finally:
            if owns_session:
                session.close()

    def is_data_safe(self, symbol: str, date_str: str, threshold: float = 0.7) -> bool:
        result = self.evaluate_symbol_date(symbol, date_str)
        return result.get("safe", False) and result.get("trust_score", 0.0) >= threshold

    def get_symbol_quality_summary(self, symbol: str) -> dict[str, Any]:
        session = self._get_session()
        owns_session = self._session is None
        try:
            stock = session.scalar(sa.select(Stock).where(Stock.symbol == symbol.upper()))
            if stock is None:
                return {
                    "symbol": symbol.upper(),
                    "total_records": 0,
                    "avg_trust_score": 0.0,
                    "unsafe_days": 0,
                    "warning_days": 0,
                    "excellent_days": 0,
                    "unsafe_pct": 0.0,
                    "common_issues": [],
                }

            records = list(
                session.scalars(
                    sa.select(DataTrust).where(DataTrust.stock_id == stock.id)
                ).all()
            )
            if not records:
                return {
                    "symbol": symbol.upper(),
                    "total_records": 0,
                    "avg_trust_score": 0.0,
                    "unsafe_days": 0,
                    "warning_days": 0,
                    "excellent_days": 0,
                    "unsafe_pct": 0.0,
                    "common_issues": [],
                }

            scores = [r.trust_score for r in records]
            unsafe_days = sum(1 for s in scores if s < 0.7)
            warning_days = sum(1 for s in scores if 0.7 <= s < 0.85)
            excellent_days = sum(1 for s in scores if s >= 0.85)
            avg_trust = sum(scores) / len(scores)

            issues: dict[str, int] = {}
            for r in records:
                if r.volume_anomaly_detected:
                    issues["volume_anomaly"] = issues.get("volume_anomaly", 0) + 1
                if (r.missing_dates_count or 0) > 0:
                    issues["missing_dates"] = issues.get("missing_dates", 0) + 1
                if (r.rejected_count or 0) > 0:
                    issues["rejected_records"] = issues.get("rejected_records", 0) + 1
                try:
                    d = json.loads(r.details or "{}")
                    if d.get("is_holiday"):
                        issues["holiday"] = issues.get("holiday", 0) + 1
                except (json.JSONDecodeError, AttributeError):
                    pass

            common_issues = sorted(issues.items(), key=lambda x: x[1], reverse=True)

            return {
                "symbol": symbol.upper(),
                "total_records": len(records),
                "avg_trust_score": avg_trust,
                "unsafe_days": unsafe_days,
                "warning_days": warning_days,
                "excellent_days": excellent_days,
                "unsafe_pct": unsafe_days / len(records),
                "common_issues": common_issues,
            }
        finally:
            if owns_session:
                session.close()

    def _compute_trust_score(
        self, session: Session, stock_id: int, price: Any
    ) -> tuple[float, dict[str, Any], dict[str, float]]:
        details: dict[str, Any] = {}
        components: dict[str, float] = {}
        trust = 1.0

        completeness = self._completeness(price)
        details["completeness_score"] = completeness
        components["completeness"] = completeness
        if completeness < 1.0:
            trust -= 0.1
            components["completeness_penalty"] = -0.1

        volume_anomaly = self._detect_volume_anomaly(session, stock_id, price)
        details["volume_anomaly"] = volume_anomaly
        volume_score = 0.8 if volume_anomaly else 1.0
        components["volume_score"] = volume_score
        if volume_anomaly:
            trust -= 0.2
            components["volume_penalty"] = -0.2

        missing_count = self._count_missing_dates(session, stock_id, price.date)
        details["missing_dates_count"] = missing_count
        missing_penalty = 0.0
        if missing_count > 0:
            missing_penalty = min(0.3, missing_count * 0.05)
            trust -= missing_penalty
        components["missing_penalty"] = -missing_penalty

        is_holiday, is_trading_day = self._is_holiday(session, price.date)
        details["is_holiday"] = is_holiday
        details["is_trading_day"] = is_trading_day
        if is_holiday:
            trust -= 0.1
            components["holiday_penalty"] = -0.1

        rejected_count = self._count_rejected(session, stock_id, price.date)
        details["rejected_count"] = rejected_count
        rejected_penalty = 0.0
        if rejected_count > 0:
            rejected_penalty = min(0.3, rejected_count * 0.02)
            trust -= rejected_penalty
        components["rejected_penalty"] = -rejected_penalty

        trust = max(0.0, min(1.0, trust))
        details["trust_score"] = trust
        components["base"] = 1.0
        components["total_penalties"] = (
            components.get("completeness_penalty", 0.0)
            + components.get("volume_penalty", 0.0)
            + components.get("missing_penalty", 0.0)
            + components.get("holiday_penalty", 0.0)
            + components.get("rejected_penalty", 0.0)
        )
        return trust, details, components

    def _classify_status(self, trust_score: float) -> str:
        if trust_score >= 0.85:
            return "excellent"
        if trust_score >= 0.7:
            return "warning"
        return "unsafe"

    def _completeness(self, price: Any) -> float:
        fields = ["open", "high", "low", "close", "volume"]
        present = sum(1 for f in fields if getattr(price, f, None) is not None)
        return present / len(fields)

    def _detect_volume_anomaly(self, session: Session, stock_id: int, price: Any) -> bool:
        if price.volume is None or price.volume <= 0:
            return False
        volumes = self._get_recent_volumes(session, stock_id, price.date, window=20)
        if len(volumes) < 5:
            return False
        mean = sum(volumes) / len(volumes)
        if mean <= 0:
            return False
        variance = sum((v - mean) ** 2 for v in volumes) / len(volumes)
        std = math.sqrt(variance)
        if std == 0:
            return abs(price.volume - mean) / mean > 0.5
        return abs(price.volume - mean) > 3 * std

    def _get_recent_volumes(
        self, session: Session, stock_id: int, before_date: Any, window: int = 20
    ) -> list[int]:
        return list(
            session.scalars(
                sa.select(Price.volume)
                .where(Price.stock_id == stock_id, Price.date < before_date)
                .order_by(Price.date.desc())
                .limit(window)
            )
        )

    def _count_missing_dates(self, session: Session, stock_id: int, target_date: Any) -> int:
        result = list(
            session.scalars(
                sa.select(Price.date)
                .where(Price.stock_id == stock_id)
                .order_by(Price.date.desc())
                .limit(30)
            ).all()
        )
        if not result:
            return 0
        dates = sorted(result)
        missing = 0
        for i in range(1, len(dates)):
            gap = (dates[i] - dates[i - 1]).days
            if gap > 1:
                missing += gap - 1
        if target_date not in dates:
            missing += 1
        return missing

    def _is_holiday(self, session: Session, target_date: Any) -> tuple[bool, bool]:
        holiday = session.scalar(
            sa.select(HolidayCalendar).where(HolidayCalendar.date == target_date)
        )
        if holiday is not None:
            expected = not holiday.is_trading_holiday
            if holiday.is_trading_day is None or holiday.is_trading_day != expected:
                holiday.is_trading_day = expected
                session.add(holiday)
                session.flush()
            return holiday.is_trading_holiday, holiday.is_trading_day
        return False, True

    def _count_rejected(self, session: Session, stock_id: int, date_str: str) -> int:
        log = session.scalar(
            sa.select(IngestionLog)
            .where(
                IngestionLog.source_id.isnot(None),
                IngestionLog.status == "failed",
            )
            .order_by(IngestionLog.completed_at.desc())
            .limit(10)
        )
        if log is None or not log.errors:
            return 0
        try:
            payload = json.loads(log.errors)
            samples = payload.get("sample_rejected", [])
            return sum(1 for s in samples if s.get("date") == date_str)
        except (json.JSONDecodeError, AttributeError):
            return 0
