from __future__ import annotations

import datetime as dt
from typing import Any

import sqlalchemy as sa
from app.db.session import session_scope
from app.models.quota import ProviderQuotaUsage
from sqlalchemy.orm import Session


class ProviderQuotaService:
    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    @staticmethod
    def _parse_date(value: str | dt.date | None) -> dt.date | None:
        if value is None or isinstance(value, dt.date):
            return value
        return dt.date.fromisoformat(value)

    def record_usage(
        self,
        provider: str,
        quota_date: str | dt.date | None = None,
        request_count: int = 1,
        signal_count: int = 0,
        updated_count: int = 0,
        success_count: int = 0,
        failure_count: int = 0,
        skipped_count: int = 0,
        token_count: int = 0,
        cost: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> ProviderQuotaUsage:
        normalized_provider = provider.strip().upper()
        if not normalized_provider:
            raise ValueError("provider is required")

        quota_day = self._parse_date(quota_date) or dt.date.today()
        with session_scope(self._session) as session:
            record = session.scalar(
                sa.select(ProviderQuotaUsage).where(
                    ProviderQuotaUsage.provider == normalized_provider,
                    ProviderQuotaUsage.quota_date == quota_day,
                )
            )
            if record is None:
                record = ProviderQuotaUsage(provider=normalized_provider, quota_date=quota_day)
                session.add(record)
                session.flush()

            record.request_count += max(0, int(request_count))
            record.signal_count += max(0, int(signal_count))
            record.updated_count += max(0, int(updated_count))
            record.success_count += max(0, int(success_count))
            record.failure_count += max(0, int(failure_count))
            record.skipped_count += max(0, int(skipped_count))
            record.token_count += max(0, int(token_count))
            record.cost = float(record.cost or 0.0) + float(cost or 0.0)
            record.updated_at = dt.datetime.now(dt.UTC)

            if metadata:
                existing_metadata = dict(record.metadata_json or {})
                existing_metadata.update(metadata)
                existing_metadata["last_updated_at"] = record.updated_at.isoformat()
                record.metadata_json = existing_metadata
            elif record.metadata_json:
                record.metadata_json["last_updated_at"] = record.updated_at.isoformat()

            session.flush()
            if self._session is None:
                session.commit()
            return record

    def get_status(
        self,
        provider: str,
        quota_date: str | dt.date | None = None,
        session: Session | None = None,
    ) -> dict[str, Any]:
        normalized_provider = provider.strip().upper()
        if not normalized_provider:
            raise ValueError("provider is required")

        quota_day = self._parse_date(quota_date) or dt.date.today()
        with session_scope(session, self._session) as sess:
            result = sess.execute(
                sa.select(
                    sa.func.coalesce(sa.func.sum(ProviderQuotaUsage.request_count), 0).label(
                        "request_count"
                    ),
                    sa.func.coalesce(sa.func.sum(ProviderQuotaUsage.signal_count), 0).label(
                        "signal_count"
                    ),
                    sa.func.coalesce(sa.func.sum(ProviderQuotaUsage.updated_count), 0).label(
                        "updated_count"
                    ),
                    sa.func.coalesce(sa.func.sum(ProviderQuotaUsage.success_count), 0).label(
                        "success_count"
                    ),
                    sa.func.coalesce(sa.func.sum(ProviderQuotaUsage.failure_count), 0).label(
                        "failure_count"
                    ),
                    sa.func.coalesce(sa.func.sum(ProviderQuotaUsage.skipped_count), 0).label(
                        "skipped_count"
                    ),
                    sa.func.coalesce(sa.func.sum(ProviderQuotaUsage.token_count), 0).label(
                        "token_count"
                    ),
                    sa.func.coalesce(sa.func.sum(ProviderQuotaUsage.cost), 0.0).label("cost"),
                )
                .where(ProviderQuotaUsage.provider == normalized_provider)
                .where(ProviderQuotaUsage.quota_date == quota_day)
            ).one()
            record = sess.scalar(
                sa.select(ProviderQuotaUsage)
                .where(ProviderQuotaUsage.provider == normalized_provider)
                .where(ProviderQuotaUsage.quota_date == quota_day)
                .order_by(ProviderQuotaUsage.updated_at.desc())
                .limit(1)
            )
            return {
                "provider": normalized_provider,
                "date": quota_day.isoformat(),
                "request_count": int(result.request_count or 0),
                "signal_count": int(result.signal_count or 0),
                "updated_count": int(result.updated_count or 0),
                "success_count": int(result.success_count or 0),
                "failure_count": int(result.failure_count or 0),
                "skipped_count": int(result.skipped_count or 0),
                "token_count": int(result.token_count or 0),
                "cost": float(result.cost or 0.0),
                "metadata": record.metadata_json if record else None,
            }

    def list_statuses(
        self,
        quota_date: str | dt.date | None = None,
        session: Session | None = None,
    ) -> list[dict[str, Any]]:
        quota_day = self._parse_date(quota_date) or dt.date.today()
        with session_scope(session, self._session) as sess:
            rows = sess.execute(
                sa.select(
                    ProviderQuotaUsage.provider,
                    sa.func.coalesce(sa.func.sum(ProviderQuotaUsage.request_count), 0).label(
                        "request_count"
                    ),
                    sa.func.coalesce(sa.func.sum(ProviderQuotaUsage.signal_count), 0).label(
                        "signal_count"
                    ),
                    sa.func.coalesce(sa.func.sum(ProviderQuotaUsage.updated_count), 0).label(
                        "updated_count"
                    ),
                    sa.func.coalesce(sa.func.sum(ProviderQuotaUsage.success_count), 0).label(
                        "success_count"
                    ),
                    sa.func.coalesce(sa.func.sum(ProviderQuotaUsage.failure_count), 0).label(
                        "failure_count"
                    ),
                    sa.func.coalesce(sa.func.sum(ProviderQuotaUsage.skipped_count), 0).label(
                        "skipped_count"
                    ),
                    sa.func.coalesce(sa.func.sum(ProviderQuotaUsage.token_count), 0).label(
                        "token_count"
                    ),
                    sa.func.coalesce(sa.func.sum(ProviderQuotaUsage.cost), 0.0).label("cost"),
                )
                .where(ProviderQuotaUsage.quota_date == quota_day)
                .group_by(ProviderQuotaUsage.provider)
                .order_by(ProviderQuotaUsage.provider)
            ).all()
            provider_names = [row.provider for row in rows]
            metadata_by_provider: dict[str, Any] = {}
            if provider_names:
                latest = (
                    sa.select(
                        ProviderQuotaUsage.provider,
                        sa.func.max(ProviderQuotaUsage.updated_at).label("updated_at"),
                    )
                    .where(ProviderQuotaUsage.quota_date == quota_day)
                    .group_by(ProviderQuotaUsage.provider)
                    .subquery()
                )
                metadata_rows = sess.execute(
                    sa.select(ProviderQuotaUsage.provider, ProviderQuotaUsage.metadata_json).join(
                        latest,
                        sa.and_(
                            ProviderQuotaUsage.provider == latest.c.provider,
                            ProviderQuotaUsage.updated_at == latest.c.updated_at,
                        ),
                    )
                ).all()
                metadata_by_provider = {
                    provider: metadata for provider, metadata in metadata_rows if metadata
                }

            return [
                {
                    "provider": row.provider,
                    "date": quota_day.isoformat(),
                    "request_count": int(row.request_count or 0),
                    "signal_count": int(row.signal_count or 0),
                    "updated_count": int(row.updated_count or 0),
                    "success_count": int(row.success_count or 0),
                    "failure_count": int(row.failure_count or 0),
                    "skipped_count": int(row.skipped_count or 0),
                    "token_count": int(row.token_count or 0),
                    "cost": float(row.cost or 0.0),
                    "metadata": metadata_by_provider.get(row.provider),
                }
                for row in rows
            ]
