from __future__ import annotations

import json
import math
from datetime import UTC, date, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from backend.app.db.session import SessionLocal
from backend.app.models.data_quality import (
    DataQualityAlert,
    DataQualityReport,
    DataTrust,
    EventOverride,
    HolidayCalendar,
    SourceCorrelation,
    SystemModeHistory,
)
from backend.app.models.data_source import DataSource, IngestionLog
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

            trust_version = details.get("trust_version", "v1")
            trust = DataTrust(
                stock_id=stock.id,
                date=price.date,
                trust_score=trust_score,
                trust_version=trust_version,
                completeness_score=details.get("completeness_score"),
                volume_anomaly_detected=details.get("volume_anomaly"),
                missing_dates_count=details.get("missing_dates_count"),
                rejected_count=details.get("rejected_count"),
                details=json.dumps(details),
            )
            session.add(trust)
            session.commit()

            self._generate_alerts(
                session, stock.id, price.date, trust_score, details, report_id=None
            )

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

    def evaluate_symbols_bulk(self, symbols: list[str], date_str: str) -> list[dict[str, Any]]:
        session = self._get_session()
        owns_session = self._session is None
        results = []
        try:
            stocks = session.scalars(
                sa.select(Stock).where(Stock.symbol.in_([s.upper() for s in symbols]))
            ).all()
            stock_map = {s.symbol: s for s in stocks}

            for symbol in symbols:
                stock = stock_map.get(symbol.upper())
                if stock is None:
                    results.append(
                        {
                            "symbol": symbol.upper(),
                            "trust_score": 0.0,
                            "status": "unsafe",
                            "safe": False,
                            "reason": "stock_not_found",
                            "components": {},
                        }
                    )
                    continue

                price = session.scalar(
                    sa.select(Price).where(
                        Price.stock_id == stock.id,
                        Price.date == date_str,
                    )
                )
                if price is None:
                    results.append(
                        {
                            "symbol": symbol.upper(),
                            "trust_score": 0.0,
                            "status": "unsafe",
                            "safe": False,
                            "reason": "no_price_data",
                            "components": {},
                        }
                    )
                    continue

                trust_score, details, components = self._compute_trust_score(
                    session, stock.id, price
                )
                status = self._classify_status(trust_score)
                is_safe = trust_score >= 0.7

                trust_version = details.get("trust_version", "v1")
                trust = DataTrust(
                    stock_id=stock.id,
                    date=price.date,
                    trust_score=trust_score,
                    trust_version=trust_version,
                    completeness_score=details.get("completeness_score"),
                    volume_anomaly_detected=details.get("volume_anomaly"),
                    missing_dates_count=details.get("missing_dates_count"),
                    rejected_count=details.get("rejected_count"),
                    details=json.dumps(details),
                )
                session.add(trust)

                results.append(
                    {
                        "symbol": symbol.upper(),
                        "trust_score": trust_score,
                        "status": status,
                        "safe": is_safe,
                        "details": details,
                        "components": components,
                    }
                )

            session.commit()
            return results
        finally:
            if owns_session:
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
                "report_id": report.id,
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

    def get_symbol_trust_trend(self, symbol: str, window: int = 30) -> dict[str, Any]:
        session = self._get_session()
        owns_session = self._session is None
        try:
            stock = session.scalar(sa.select(Stock).where(Stock.symbol == symbol.upper()))
            if stock is None:
                return {"symbol": symbol.upper(), "trend": None}

            records = list(
                session.scalars(
                    sa.select(DataTrust)
                    .where(DataTrust.stock_id == stock.id)
                    .order_by(DataTrust.date.desc())
                    .limit(window)
                ).all()
            )

            if not records:
                return {"symbol": symbol.upper(), "trend": None}

            scores = [r.trust_score for r in records]
            recent_7 = scores[:7] if len(scores) >= 7 else scores
            avg_7d = sum(recent_7) / len(recent_7) if recent_7 else 0.0
            unsafe_pct = sum(1 for s in scores if s < 0.7) / len(scores)
            std_dev = self._std_dev(scores)

            return {
                "symbol": symbol.upper(),
                "trend": {
                    "avg_7d": avg_7d,
                    "avg_30d": sum(scores) / len(scores),
                    "stability": std_dev,
                    "unsafe_pct": unsafe_pct,
                    "total_days": len(scores),
                },
            }
        finally:
            if owns_session:
                session.close()

    def _std_dev(self, values: list[float]) -> float:
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        return math.sqrt(variance)

    def check_data_freshness(
        self, symbol: str, target_date: str, expected_hours: float = 16.0
    ) -> dict[str, Any]:
        session = self._get_session()
        owns_session = self._session is None
        try:
            stock = session.scalar(sa.select(Stock).where(Stock.symbol == symbol.upper()))
            if stock is None:
                return {"symbol": symbol.upper(), "fresh": False, "reason": "stock_not_found"}

            latest_price = session.scalar(
                sa.select(Price)
                .where(Price.stock_id == stock.id)
                .order_by(Price.date.desc())
                .limit(1)
            )

            if latest_price is None:
                return {"symbol": symbol.upper(), "fresh": False, "reason": "no_data"}

            target = datetime.strptime(target_date, "%Y-%m-%d").date()
            if latest_price.date < target:
                return {
                    "symbol": symbol.upper(),
                    "fresh": False,
                    "reason": "DATA_DELAY",
                    "last_update": latest_price.date.isoformat(),
                    "expected_date": target_date,
                }

            return {
                "symbol": symbol.upper(),
                "fresh": True,
                "last_update": latest_price.date.isoformat(),
            }
        finally:
            if owns_session:
                session.close()

    def cross_validate_sources(
        self, symbol: str, date_str: str, price_field: str = "close"
    ) -> dict[str, Any]:
        session = self._get_session()
        owns_session = self._session is None
        try:
            stock = session.scalar(sa.select(Stock).where(Stock.symbol == symbol.upper()))
            if stock is None:
                return {"symbol": symbol.upper(), "match": False, "reason": "stock_not_found"}

            price = session.scalar(
                sa.select(Price).where(
                    Price.stock_id == stock.id,
                    Price.date == datetime.strptime(date_str, "%Y-%m-%d").date(),
                )
            )
            if price is None:
                return {"symbol": symbol.upper(), "match": False, "reason": "no_price_data"}

            sources = list(session.scalars(sa.select(DataSource)).all())
            if len(sources) < 2:
                return {"symbol": symbol.upper(), "match": True, "reason": "single_source"}

            values_by_source: dict[str, float] = {}
            for source in sources:
                log = session.scalar(
                    sa.select(IngestionLog)
                    .where(IngestionLog.source_id == source.id)
                    .order_by(IngestionLog.completed_at.desc())
                    .limit(1)
                )
                if log and log.errors:
                    try:
                        payload = json.loads(log.errors)
                        samples = payload.get("sample_rejected", [])
                        for sample in samples:
                            if (
                                sample.get("date") == date_str
                                and sample.get("symbol") == symbol.upper()
                            ):
                                val = sample.get(price_field)
                                if val is not None:
                                    values_by_source[source.name] = float(val)
                    except (json.JSONDecodeError, ValueError, TypeError):
                        pass

            if len(values_by_source) < 2:
                return {
                    "symbol": symbol.upper(),
                    "match": True,
                    "reason": "insufficient_data",
                    "note": "Only one source has data for this date",
                }

            vals = list(values_by_source.values())
            current_val = float(getattr(price, price_field) or 0)
            if current_val == 0:
                return {
                    "symbol": symbol.upper(),
                    "match": False,
                    "reason": "no_current_value",
                }

            if all(abs(v - current_val) / current_val < 0.05 for v in vals):
                return {
                    "symbol": symbol.upper(),
                    "match": True,
                    "field": price_field,
                    "value": current_val,
                    "sources_checked": list(values_by_source.keys()),
                    "max_deviation_pct": max(abs(v - current_val) / current_val for v in vals)
                    * 100,
                }

            return {
                "symbol": symbol.upper(),
                "match": False,
                "field": price_field,
                "value": current_val,
                "sources_checked": list(values_by_source.keys()),
                "discrepancies": {
                    k: v
                    for k, v in values_by_source.items()
                    if abs(v - current_val) / current_val >= 0.05
                },
            }
        finally:
            if owns_session:
                session.close()

    def get_alerts(
        self, report_id: int | None = None, acknowledged: bool = False
    ) -> list[dict[str, Any]]:
        session = self._get_session()
        owns_session = self._session is None
        try:
            query = sa.select(DataQualityAlert)
            if report_id is not None:
                query = query.where(DataQualityAlert.report_id == report_id)
            if acknowledged:
                query = query.where(DataQualityAlert.acknowledged.is_(True))
            alerts = session.scalars(query.order_by(DataQualityAlert.created_at.desc())).all()
            return [
                {
                    "id": a.id,
                    "report_id": a.report_id,
                    "symbol": a.symbol,
                    "date": a.date.isoformat(),
                    "severity": a.severity,
                    "message": a.message,
                    "acknowledged": a.acknowledged,
                    "created_at": a.created_at.isoformat(),
                }
                for a in alerts
            ]
        finally:
            if owns_session:
                session.close()

    def acknowledge_alert(self, alert_id: int) -> bool:
        session = self._get_session()
        owns_session = self._session is None
        try:
            alert = session.get(DataQualityAlert, alert_id)
            if alert is None:
                return False
            alert.acknowledged = True
            session.commit()
            return True
        finally:
            if owns_session:
                session.close()

    def get_system_mode(self) -> dict[str, Any]:
        session = self._get_session()
        owns_session = self._session is None
        try:
            stocks = list(session.scalars(sa.select(Stock)).all())
            if not stocks:
                mode_result = {
                    "mode": "SAFE_MODE",
                    "reason": "no_symbols",
                    "unsafe_ratio": 0.0,
                }
                self._persist_system_mode(session, mode_result)
                return mode_result

            unsafe_count = 0
            for stock in stocks:
                trust = session.scalar(
                    sa.select(DataTrust)
                    .where(DataTrust.stock_id == stock.id)
                    .order_by(DataTrust.date.desc())
                    .limit(1)
                )
                if trust is None or trust.trust_score < 0.7:
                    unsafe_count += 1

            unsafe_ratio = unsafe_count / len(stocks)

            if unsafe_ratio >= 0.5:
                mode = "SAFE_MODE"
            elif unsafe_ratio >= 0.2:
                mode = "DEGRADED"
            else:
                mode = "NORMAL"

            mode_result = {
                "mode": mode,
                "total_symbols": len(stocks),
                "unsafe_count": unsafe_count,
                "unsafe_ratio": unsafe_ratio,
            }
            self._persist_system_mode(session, mode_result)
            return mode_result
        finally:
            if owns_session:
                session.close()

    def _persist_system_mode(self, session: Session, mode_result: dict[str, Any]) -> None:
        history = SystemModeHistory(
            timestamp=datetime.now(UTC),
            mode=mode_result["mode"],
            unsafe_ratio=mode_result["unsafe_ratio"],
            total_symbols=mode_result.get("total_symbols", 0),
        )
        session.add(history)
        session.commit()

    def get_source_accuracy_score(self, source_id: int) -> float:
        session = self._get_session()
        owns_session = self._session is None
        try:
            logs = list(
                session.scalars(
                    sa.select(IngestionLog)
                    .where(IngestionLog.source_id == source_id)
                    .order_by(IngestionLog.completed_at.desc())
                    .limit(100)
                ).all()
            )
            if not logs:
                return 1.0

            success_count = sum(1 for log in logs if log.status == "success")
            success_rate = success_count / len(logs)
            avg_rejected = sum(log.records_rejected for log in logs) / len(logs)
            rejection_penalty = min(0.3, avg_rejected / 100.0)
            return max(0.0, success_rate - rejection_penalty)
        finally:
            if owns_session:
                session.close()

    def calculate_weighted_price(
        self, symbol: str, date_str: str, price_field: str = "close"
    ) -> float | None:
        session = self._get_session()
        owns_session = self._session is None
        try:
            stock = session.scalar(sa.select(Stock).where(Stock.symbol == symbol.upper()))
            if stock is None:
                return None

            price = session.scalar(
                sa.select(Price).where(
                    Price.stock_id == stock.id,
                    Price.date == datetime.strptime(date_str, "%Y-%m-%d").date(),
                )
            )
            if price is None:
                return None

            sources = list(
                session.scalars(sa.select(DataSource).where(DataSource.is_active.is_(True))).all()
            )
            if not sources:
                return float(getattr(price, price_field) or 0)

            values_with_weights: list[tuple[float, float]] = []
            for source in sources:
                accuracy = source.accuracy_score if source.accuracy_score else 1.0
                if accuracy < 0.3:
                    continue
                val = getattr(price, price_field, None)
                if val is not None:
                    values_with_weights.append((float(val), accuracy))

            if not values_with_weights:
                return None

            weighted_sum = sum(v * w for v, w in values_with_weights)
            total_weight = sum(w for _, w in values_with_weights)
            return weighted_sum / total_weight if total_weight > 0 else None
        finally:
            if owns_session:
                session.close()

    def detect_source_drift(self, source_id: int, window: int = 10) -> dict[str, Any]:
        session = self._get_session()
        owns_session = self._session is None
        try:
            logs = list(
                session.scalars(
                    sa.select(IngestionLog)
                    .where(
                        IngestionLog.source_id == source_id,
                        IngestionLog.status == "success",
                    )
                    .order_by(IngestionLog.completed_at.desc())
                    .limit(200)
                ).all()
            )
            if len(logs) < window * 2:
                return {
                    "source_id": source_id,
                    "drift_detected": False,
                    "reason": "insufficient_data",
                    "current_stats": {"records_inserted_avg": 0},
                }

            recent = logs[:window]
            historical = logs[window : window * 2]

            current_avg = sum(log.records_inserted for log in recent) / len(recent)
            historical_avg = sum(log.records_inserted for log in historical) / len(historical)

            if historical_avg == 0:
                drift = current_avg > 0 and current_avg < 50
            else:
                drift = current_avg < historical_avg * 0.7

            return {
                "source_id": source_id,
                "drift_detected": drift,
                "current_stats": {
                    "records_inserted_avg": current_avg,
                    "records_fetched_avg": sum(log.records_fetched for log in recent) / len(recent),
                },
                "historical_stats": {
                    "records_inserted_avg": historical_avg,
                },
                "ratio": current_avg / historical_avg if historical_avg > 0 else 0,
            }
        finally:
            if owns_session:
                session.close()

    def recover_blacklisted_sources(self, recovery_threshold: float = 0.5) -> list[dict[str, Any]]:
        session = self._get_session()
        owns_session = self._session is None
        recovered = []
        try:
            sources = list(
                session.scalars(
                    sa.select(DataSource).where(
                        DataSource.is_active.is_(False),
                        DataSource.accuracy_score < 0.3,
                    )
                ).all()
            )

            for source in sources:
                accuracy = self.get_source_accuracy_score(source.id)
                if accuracy >= recovery_threshold:
                    source.is_active = True
                    source.accuracy_score = accuracy
                    session.add(source)
                    recovered.append(
                        {
                            "source_id": source.id,
                            "name": source.name,
                            "accuracy_score": accuracy,
                            "recovered": True,
                        }
                    )

            session.commit()
            return recovered
        finally:
            if owns_session:
                session.close()

    def apply_trust_decay(self, days_threshold: int = 30, decay_factor: float = 0.95) -> int:
        session = self._get_session()
        owns_session = self._session is None
        decayed_count = 0
        try:
            threshold_date = datetime.now(UTC).date() - timedelta(days=days_threshold)
            old_trusts = list(
                session.scalars(sa.select(DataTrust).where(DataTrust.date <= threshold_date)).all()
            )

            for trust in old_trusts:
                new_score = max(0.0, trust.trust_score * decay_factor)
                if new_score != trust.trust_score:
                    trust.trust_score = new_score
                    session.add(trust)
                    decayed_count += 1

            session.commit()
            return decayed_count
        finally:
            if owns_session:
                session.close()

    def _generate_alerts(
        self,
        session: Session,
        stock_id: int,
        date: date,
        trust_score: float,
        details: dict[str, Any],
        report_id: int | None,
    ) -> None:
        symbol = session.scalar(sa.select(Stock).where(Stock.id == stock_id))
        if symbol is None:
            return

        if trust_score < 0.7:
            severity = "critical" if trust_score < 0.3 else "warning"
            self._create_alert(
                session,
                report_id,
                symbol.symbol,
                date,
                severity,
                f"Low trust score: {trust_score:.2f}",
                metadata={"type": "TRUST_SCORE_LOW", "value": trust_score},
            )

        if details.get("volume_anomaly"):
            volume = details.get("volume_actual", 0)
            volume_mean = details.get("volume_mean", 0)
            z_score = details.get("volume_z_score", 0)
            self._create_alert(
                session,
                report_id,
                symbol.symbol,
                date,
                "warning",
                "Volume anomaly detected",
                metadata={
                    "type": "VOLUME_ANOMALY",
                    "actual": volume,
                    "expected_mean": volume_mean,
                    "z_score": z_score,
                },
            )

        if (details.get("missing_dates_count", 0) or 0) > 3:
            missing = details.get("missing_dates_count", 0)
            self._create_alert(
                session,
                report_id,
                symbol.symbol,
                date,
                "warning",
                f"Missing {missing} trading days detected",
                metadata={"type": "MISSING_DAYS", "count": missing},
            )

        if (details.get("rejected_count", 0) or 0) > 0:
            rejected = details.get("rejected_count", 0)
            self._create_alert(
                session,
                report_id,
                symbol.symbol,
                date,
                "info",
                f"{rejected} records rejected during ingestion",
                metadata={"type": "REJECTED_RECORDS", "count": rejected},
            )

    def _create_alert(
        self,
        session: Session,
        report_id: int | None,
        symbol: str,
        date: date,
        severity: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        alert = DataQualityAlert(
            report_id=report_id or 0,
            symbol=symbol,
            date=date,
            severity=severity,
            message=message,
            details=json.dumps(metadata) if metadata else None,
            created_at=datetime.now(UTC),
        )
        session.add(alert)
        session.flush()

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
                session.scalars(sa.select(DataTrust).where(DataTrust.stock_id == stock.id)).all()
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

        volume_anomaly, volume_actual, volume_mean, volume_z = self._detect_volume_anomaly_detailed(
            session, stock_id, price
        )
        details["volume_anomaly"] = volume_anomaly
        details["volume_actual"] = volume_actual
        details["volume_mean"] = volume_mean
        details["volume_z_score"] = volume_z
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

    def _detect_volume_anomaly_detailed(
        self, session: Session, stock_id: int, price: Any
    ) -> tuple[bool, int, float, float]:
        if price.volume is None or price.volume <= 0:
            return False, 0, 0.0, 0.0
        volumes = self._get_recent_volumes(session, stock_id, price.date, window=20)
        if len(volumes) < 5:
            return False, int(price.volume), 0.0, 0.0
        mean = sum(volumes) / len(volumes)
        if mean <= 0:
            return False, int(price.volume), 0.0, 0.0
        variance = sum((v - mean) ** 2 for v in volumes) / len(volumes)
        std = math.sqrt(variance)
        if std == 0:
            is_anomaly = abs(price.volume - mean) / mean > 0.5
            z_score = abs(price.volume - mean) / mean if mean > 0 else 0.0
            return is_anomaly, int(price.volume), mean, z_score
        z_score = abs(price.volume - mean) / std if std > 0 else 0.0
        is_anomaly = z_score > 3
        return is_anomaly, int(price.volume), mean, z_score

    def _detect_volume_anomaly(self, session: Session, stock_id: int, price: Any) -> bool:
        is_anomaly, _, _, _ = self._detect_volume_anomaly_detailed(session, stock_id, price)
        return is_anomaly

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

    def compute_trust_score_with_version(
        self, session: Session, stock_id: int, price: Any, trust_version: str = "v1"
    ) -> tuple[float, dict[str, Any], dict[str, float]]:
        if trust_version == "v2":
            return self._compute_trust_score_v2(session, stock_id, price)
        if trust_version == "v3":
            return self._compute_trust_score_v3(session, stock_id, price)
        return self._compute_trust_score(session, stock_id, price)

    def _compute_trust_score_v2(
        self, session: Session, stock_id: int, price: Any
    ) -> tuple[float, dict[str, Any], dict[str, float]]:
        trust_score, details, components = self._compute_trust_score(session, stock_id, price)
        details["trust_version"] = "v2"
        if details.get("volume_anomaly"):
            trust_score = trust_score * 0.98
            components["v2_penalty"] = -0.02 * trust_score
        return trust_score, details, components

    def _compute_trust_score_v3(
        self, session: Session, stock_id: int, price: Any
    ) -> tuple[float, dict[str, Any], dict[str, float]]:
        trust_score, details, components = self._compute_trust_score(session, stock_id, price)
        details["trust_version"] = "v3"
        if details.get("volume_anomaly") and details.get("is_holiday"):
            trust_score = trust_score * 0.95
            components["v3_holiday_penalty"] = -0.05 * trust_score
        return trust_score, details, components

    def detect_source_correlations(
        self, symbols: list[str] | None = None, window_days: int = 30, threshold: float = 0.8
    ) -> list[dict[str, Any]]:
        session = self._get_session()
        owns_session = self._session is None
        try:
            sources = session.scalars(sa.select(DataSource)).all()
            if len(sources) < 2:
                return []

            correlations = []
            for i, src_a in enumerate(sources):
                for src_b in sources[i + 1 :]:
                    correlation = self._compute_source_correlation(
                        session, src_a.id, src_b.id, symbols, window_days
                    )
                    if correlation >= threshold:
                        correlations.append(
                            {
                                "source_a": src_a.name,
                                "source_b": src_b.name,
                                "correlation": correlation,
                            }
                        )
                        self._persist_source_correlation(session, src_a.id, src_b.id, correlation)

            return correlations
        finally:
            if owns_session:
                session.close()

    def _compute_source_correlation(
        self,
        session: Session,
        source_a_id: int,
        source_b_id: int,
        symbols: list[str] | None = None,
        window_days: int = 30,
    ) -> float:
        cutoff_date = datetime.now(UTC) - timedelta(days=window_days)
        log_a = session.scalar(
            sa.select(IngestionLog)
            .where(
                IngestionLog.source_id == source_a_id,
                IngestionLog.completed_at >= cutoff_date,
            )
            .order_by(IngestionLog.completed_at.desc())
            .limit(1)
        )
        log_b = session.scalar(
            sa.select(IngestionLog)
            .where(
                IngestionLog.source_id == source_b_id,
                IngestionLog.completed_at >= cutoff_date,
            )
            .order_by(IngestionLog.completed_at.desc())
            .limit(1)
        )

        if log_a is None or log_b is None:
            return 0.0

        try:
            errors_a = json.loads(log_a.errors or "{}")
            errors_b = json.loads(log_b.errors or "{}")
        except (json.JSONDecodeError, TypeError):
            return 0.0

        samples_a = errors_a.get("sample_rejected", [])
        samples_b = errors_b.get("sample_rejected", [])

        if not samples_a or not samples_b:
            return 0.0

        if symbols:
            symbol_set = {s.upper() for s in symbols}
            dates_a = set(
                s.get("date")
                for s in samples_a
                if s.get("date") and s.get("symbol", "").upper() in symbol_set
            )
            dates_b = set(
                s.get("date")
                for s in samples_b
                if s.get("date") and s.get("symbol", "").upper() in symbol_set
            )
        else:
            dates_a = set(s.get("date") for s in samples_a if s.get("date"))
            dates_b = set(s.get("date") for s in samples_b if s.get("date"))

        if not dates_a or not dates_b:
            return 0.0

        common = len(dates_a & dates_b)
        union = len(dates_a | dates_b)
        return common / union if union > 0 else 0.0

    def _persist_source_correlation(
        self, session: Session, source_a_id: int, source_b_id: int, correlation: float
    ) -> None:
        existing = session.scalar(
            sa.select(SourceCorrelation).where(
                SourceCorrelation.source_a_id.in_([source_a_id, source_b_id]),
                SourceCorrelation.source_b_id.in_([source_a_id, source_b_id]),
            )
        )
        if existing:
            existing.correlation_score = correlation
            existing.last_sync_detected = datetime.now(UTC)
            existing.detection_count += 1
            session.add(existing)
        else:
            corr = SourceCorrelation(
                source_a_id=source_a_id,
                source_b_id=source_b_id,
                correlation_score=correlation,
                last_sync_detected=datetime.now(UTC),
            )
            session.add(corr)
        session.flush()

    def create_event_override(
        self,
        event_type: str,
        date_str: str,
        sensitivity_multiplier: float,
        reason: str,
        symbol: str | None = None,
        expires_hours: int | None = None,
    ) -> dict[str, Any]:
        session = self._get_session()
        owns_session = self._session is None
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            expires_at = None
            if expires_hours:
                expires_at = datetime.now(UTC) + timedelta(hours=expires_hours)

            override = EventOverride(
                event_type=event_type,
                date=target_date,
                symbol=symbol.upper() if symbol else None,
                sensitivity_multiplier=sensitivity_multiplier,
                reason=reason,
                created_at=datetime.now(UTC),
                expires_at=expires_at,
            )
            session.add(override)
            session.commit()

            return {
                "id": override.id,
                "event_type": override.event_type,
                "date": override.date.isoformat(),
                "symbol": override.symbol,
                "sensitivity_multiplier": override.sensitivity_multiplier,
            }
        finally:
            if owns_session:
                session.close()

    def get_active_event_overrides(
        self, date_str: str, symbol: str | None = None
    ) -> list[dict[str, Any]]:
        session = self._get_session()
        owns_session = self._session is None
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            query = sa.select(EventOverride).where(EventOverride.date == target_date)
            if symbol:
                query = query.where(EventOverride.symbol == symbol.upper())
            overrides = session.scalars(query).all()

            now = datetime.now(UTC)
            active = []
            for o in overrides:
                if o.expires_at is None:
                    is_active = True
                elif o.expires_at.tzinfo is None:
                    is_active = o.expires_at.replace(tzinfo=UTC) > now
                else:
                    is_active = o.expires_at > now

                if is_active:
                    active.append(
                        {
                            "event_type": o.event_type,
                            "date": o.date.isoformat(),
                            "symbol": o.symbol,
                            "sensitivity_multiplier": o.sensitivity_multiplier,
                            "reason": o.reason,
                        }
                    )
            return active
        finally:
            if owns_session:
                session.close()

    def evaluate_with_event_override(
        self, symbol: str, date_str: str, session: Session | None = None
    ) -> dict[str, Any]:
        owns_session = session is None
        if owns_session:
            session = self._get_session()
        try:
            overrides = self.get_active_event_overrides(date_str, symbol)
            multiplier = 1.0
            for o in overrides:
                multiplier *= o["sensitivity_multiplier"]

            result = self.evaluate_symbol_date(symbol, date_str, session=session)
            if overrides:
                result["event_adjusted"] = True
                result["original_trust_score"] = result["trust_score"]
                result["trust_score"] = max(0.0, min(1.0, result["trust_score"] * multiplier))
                result["sensitivity_multiplier"] = multiplier

            return result
        finally:
            if owns_session:
                session.close()
