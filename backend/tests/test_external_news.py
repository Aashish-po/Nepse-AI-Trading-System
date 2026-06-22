"""News ingestion tests (offline, via httpx.MockTransport)."""

from __future__ import annotations

import httpx
import sqlalchemy as sa
from app.core.config import Settings
from app.models.data_source import IngestionLog
from app.models.news import NewsArticle, NewsMention
from app.services.external.newsapi import NewsApiClient
from app.services.external_news import NewsIngestionService, canonical_url_hash


def _enabled_cfg() -> Settings:
    return Settings(newsapi_enabled=True, newsapi_api_key="testkey")  # type: ignore[call-arg]


def _articles_handler(articles: list[dict]):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok", "articles": articles})

    return handler


def _client(handler) -> NewsApiClient:
    return NewsApiClient(
        _enabled_cfg(), client=httpx.Client(transport=httpx.MockTransport(handler))
    )


def _article(url: str, title: str = "Bank profit surges", published: str = "2024-06-01T10:00:00Z"):
    return {"url": url, "title": title, "source": {"name": "Wire"}, "publishedAt": published}


def test_canonical_url_hash_normalizes() -> None:
    # Trailing slash, fragment, and case must not change identity.
    assert canonical_url_hash("https://x.com/a/") == canonical_url_hash("https://X.com/a#frag")


def test_disabled_provider_skips_without_calls(db_session) -> None:
    svc = NewsIngestionService(Settings(newsapi_enabled=False), session=db_session)  # type: ignore[call-arg]
    result = svc.run({"NABIL": "Nabil Bank"})
    assert result["status"] == "skipped"
    assert result["reason"] == "provider_disabled"


def test_ingest_stores_articles_and_mentions(db_session) -> None:
    handler = _articles_handler([_article("https://news.test/1"), _article("https://news.test/2")])
    svc = NewsIngestionService(_enabled_cfg(), session=db_session, client=_client(handler))
    result = svc.run({"NABIL": "Nabil Bank"})

    assert result["status"] == "success"
    assert result["inserted"] == 2
    articles = db_session.scalars(sa.select(NewsArticle)).all()
    assert len(articles) == 2
    mentions = db_session.scalars(sa.select(NewsMention)).all()
    assert {m.symbol for m in mentions} == {"NABIL"}
    log = db_session.scalar(sa.select(IngestionLog).where(IngestionLog.source == "newsapi"))
    assert log is not None and log.status == "success"


def test_ingest_dedups_by_url_hash(db_session) -> None:
    # Same URL with differing trailing slash/case -> one article row.
    handler = _articles_handler(
        [_article("https://news.test/dup"), _article("https://NEWS.test/dup/")]
    )
    svc = NewsIngestionService(_enabled_cfg(), session=db_session, client=_client(handler))
    result = svc.run({"NABIL": "Nabil Bank"})
    assert result["inserted"] == 1
    assert db_session.scalar(sa.select(sa.func.count()).select_from(NewsArticle)) == 1


def test_ingest_skips_empty_url(db_session) -> None:
    handler = _articles_handler([{"url": "", "title": "no url"}, _article("https://news.test/ok")])
    svc = NewsIngestionService(_enabled_cfg(), session=db_session, client=_client(handler))
    result = svc.run({"NABIL": "Nabil Bank"})
    assert result["inserted"] == 1


def test_second_run_same_article_adds_no_duplicate(db_session) -> None:
    handler = _articles_handler([_article("https://news.test/1")])
    svc = NewsIngestionService(_enabled_cfg(), session=db_session, client=_client(handler))
    svc.run({"NABIL": "Nabil Bank"})
    # Re-run: idempotent.
    svc2 = NewsIngestionService(_enabled_cfg(), session=db_session, client=_client(handler))
    result = svc2.run({"NABIL": "Nabil Bank"})
    assert result["inserted"] == 0
    assert db_session.scalar(sa.select(sa.func.count()).select_from(NewsArticle)) == 1
