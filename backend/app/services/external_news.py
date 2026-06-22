"""News ingestion service (NewsAPI).

Fetches articles for a set of per-symbol search queries, de-duplicates by
canonical-URL hash, and stores them in ``news_articles`` with a ``news_mentions``
row linking each article to the symbol it was fetched for. Every run is recorded
in ``IngestionLog``. Provider/network failures are logged and surfaced in the
returned summary but never raised into feature generation or fusion.

Manual / on-demand only (no scheduler).
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from app.core.config import Settings, settings as default_settings
from app.db.session import SessionLocal
from app.models.data_source import IngestionLog
from app.models.news import NewsArticle, NewsMention
from app.services.external.newsapi import PROVIDER as NEWSAPI_PROVIDER, NewsApiClient
from app.services.external.providers import PROVIDERS_BY_KEY, ensure_data_source, is_enabled
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def canonical_url_hash(url: str) -> str:
    """Stable identity for an article URL (lower-cased, fragment/trailing-slash
    stripped) so re-fetching the same article is idempotent."""
    canonical = url.strip().split("#", 1)[0].rstrip("/").lower()
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class NewsIngestionService:
    """Ingest NewsAPI articles for a mapping of ``symbol -> search query``."""

    def __init__(
        self,
        cfg: Settings | None = None,
        *,
        session: Session | None = None,
        client: NewsApiClient | None = None,
    ) -> None:
        self._cfg = cfg or default_settings
        self._session = session
        self._client = client

    def _get_session(self) -> Session:
        return self._session if self._session is not None else SessionLocal()

    def run(
        self,
        query_by_symbol: dict[str, str],
        *,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict[str, Any]:
        """Fetch + store articles for each ``symbol -> query``.

        Returns a summary dict; never raises on provider failure.
        """
        spec = PROVIDERS_BY_KEY["newsapi"]
        if not is_enabled(spec, self._cfg):
            logger.info("news ingest skipped: NewsAPI not enabled/keyed")
            return {"status": "skipped", "reason": "provider_disabled", "symbols": {}}

        session = self._get_session()
        owns_session = self._session is None
        client = self._client or NewsApiClient(self._cfg)
        owns_client = self._client is None

        start_time = datetime.now(UTC)
        log = IngestionLog(
            source=NEWSAPI_PROVIDER,
            status="failed",
            started_at=start_time,
            completed_at=start_time,
        )
        session.add(log)
        session.commit()
        log_id = log.id
        del log

        ensure_data_source(session, spec)
        session.commit()

        per_symbol: dict[str, Any] = {}
        total_fetched = 0
        total_inserted = 0
        try:
            for symbol, query in query_by_symbol.items():
                result = self._ingest_one(
                    session, client, symbol.upper(), query, from_date, to_date
                )
                per_symbol[symbol] = result
                total_fetched += result.get("fetched", 0)
                total_inserted += result.get("inserted", 0)

            completed_at = datetime.now(UTC)
            failed = [s for s, r in per_symbol.items() if r.get("status") == "failed"]
            session.query(IngestionLog).filter(IngestionLog.id == log_id).update(
                {
                    "status": "success",
                    "records_fetched": total_fetched,
                    "records_inserted": total_inserted,
                    "records_rejected": total_fetched - total_inserted,
                    "duration_seconds": (completed_at - start_time).total_seconds(),
                    "errors": json.dumps({"failed_symbols": failed}) if failed else None,
                    "completed_at": completed_at,
                }
            )
            session.commit()
            return {
                "status": "success",
                "fetched": total_fetched,
                "inserted": total_inserted,
                "symbols": per_symbol,
            }
        except Exception as exc:  # noqa: BLE001 — provider failure must not propagate
            completed_at = datetime.now(UTC)
            session.query(IngestionLog).filter(IngestionLog.id == log_id).update(
                {
                    "status": "failed",
                    "records_fetched": total_fetched,
                    "records_inserted": total_inserted,
                    "duration_seconds": (completed_at - start_time).total_seconds(),
                    "errors": json.dumps({"exception": str(exc)}),
                    "completed_at": completed_at,
                }
            )
            session.commit()
            logger.exception("news ingest failed")
            return {
                "status": "failed",
                "error": str(exc),
                "fetched": total_fetched,
                "inserted": total_inserted,
                "symbols": per_symbol,
            }
        finally:
            if owns_client:
                client.close()
            if owns_session:
                session.close()

    def _ingest_one(
        self,
        session: Session,
        client: NewsApiClient,
        symbol: str,
        query: str,
        from_date: str | None,
        to_date: str | None,
    ) -> dict[str, Any]:
        try:
            rows = client.everything(query, from_date=from_date, to_date=to_date)
            inserted = 0
            for row in rows:
                if self._upsert_article(session, symbol, row):
                    inserted += 1
            session.commit()
            return {"status": "success", "fetched": len(rows), "inserted": inserted}
        except Exception as exc:  # noqa: BLE001
            logger.warning("news fetch for %s failed: %s", symbol, exc)
            session.rollback()
            return {"status": "failed", "error": str(exc), "fetched": 0, "inserted": 0}

    def _upsert_article(self, session: Session, symbol: str, row: dict[str, Any]) -> bool:
        """Insert the article if new (by url_hash) and ensure a symbol mention.

        Returns True when a *new* article row was created.
        """
        url_hash = canonical_url_hash(row["url"])
        created = False
        try:
            with session.begin_nested():
                article = session.scalar(
                    sa.select(NewsArticle).where(NewsArticle.url_hash == url_hash)
                )
                if article is None:
                    article = NewsArticle(
                        provider=row.get("provider", NEWSAPI_PROVIDER),
                        url=row["url"],
                        url_hash=url_hash,
                        title=row.get("title"),
                        source=row.get("source"),
                        published_date=row.get("published_date"),
                        body_text=row.get("body_text"),
                        raw_json=row.get("raw"),
                    )
                    session.add(article)
                    session.flush()
                    created = True
                self._ensure_mention(session, article.id, symbol)
        except SQLAlchemyError as exc:
            logger.warning("article upsert failed (%s): %s", url_hash[:12], exc)
            return False
        return created

    @staticmethod
    def _ensure_mention(session: Session, article_id: int, symbol: str) -> None:
        existing = session.scalar(
            sa.select(NewsMention).where(
                NewsMention.article_id == article_id, NewsMention.symbol == symbol
            )
        )
        if existing is None:
            session.add(NewsMention(article_id=article_id, symbol=symbol))
            session.flush()
