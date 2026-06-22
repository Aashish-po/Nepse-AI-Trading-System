"""NewsAPI client.

Fetches headlines/articles and normalises them to the news contract:

    {provider, title, url, source, published_date (date|None),
     body_text, raw}

URLs are required (articles without one are skipped). Canonical-URL de-dup is
handled downstream via ``url_hash`` (see :mod:`app.services.external_news`).
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

import httpx
from app.core.config import Settings, settings as default_settings
from app.services.external.base import ExternalApiClient

logger = logging.getLogger(__name__)

PROVIDER = "newsapi"


class NewsApiClient(ExternalApiClient):
    def __init__(
        self,
        cfg: Settings | None = None,
        *,
        client: httpx.Client | None = None,
        **kwargs: Any,
    ) -> None:
        cfg = cfg or default_settings
        super().__init__(
            provider=PROVIDER,
            base_url=cfg.newsapi_base_url,
            api_key=cfg.newsapi_api_key,
            # NewsAPI accepts the key via the X-Api-Key header.
            auth_header="X-Api-Key",
            rate_limit_per_minute=cfg.newsapi_rate_limit_per_minute,
            client=client,
            **kwargs,
        )

    def everything(
        self,
        query: str,
        *,
        from_date: str | None = None,
        to_date: str | None = None,
        language: str = "en",
        page_size: int = 50,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"q": query, "language": language, "pageSize": page_size}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        data = self.get_json("/v2/everything", params=params)
        return self._normalize(data)

    def top_headlines(self, query: str, *, language: str = "en", page_size: int = 50) -> list[dict]:
        data = self.get_json(
            "/v2/top-headlines",
            params={"q": query, "language": language, "pageSize": page_size},
        )
        return self._normalize(data)

    @staticmethod
    def _normalize(data: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for art in data.get("articles") or []:
            url = (art.get("url") or "").strip()
            if not url:
                continue  # URL is required for identity/dedup
            rows.append(
                {
                    "provider": PROVIDER,
                    "title": art.get("title"),
                    "url": url,
                    "source": (art.get("source") or {}).get("name"),
                    "published_date": _parse_published(art.get("publishedAt")),
                    "body_text": art.get("description") or art.get("content"),
                    "raw": art,
                }
            )
        return rows


def _parse_published(raw: Any) -> date | None:
    if not raw:
        return None
    text = str(raw)
    try:
        # NewsAPI uses ISO-8601 with a trailing Z.
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None
