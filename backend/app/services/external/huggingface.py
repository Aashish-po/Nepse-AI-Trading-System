"""Hugging Face hosted-inference client + sentiment backend adapter.

Provides optional NLP enrichment for the news-sentiment pipeline. The client
POSTs text to the configured hosted model and normalises the response to a
bounded 0-1 bullishness score. ``HuggingFaceSentimentBackend`` conforms to the
backend protocol used by :class:`ml.sentiment.SentimentAnalyzer` (``score(text)``
returning a ``SentimentBackendResult`` plus ``backend_name``/``model_version``),
so it can be injected as the analyzer's primary backend. The analyzer's existing
try/except then degrades to the lexicon backend automatically on any HF failure.

No key logging; auth via ``Authorization: Bearer``. Disabled by default.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from app.core.config import Settings, settings as default_settings
from app.services.external.base import ExternalApiClient

from ml.sentiment import SentimentBackendResult

logger = logging.getLogger(__name__)

PROVIDER = "huggingface"

# Label fragments → polarity direction. HF sentiment models use varied schemes
# (POSITIVE/NEGATIVE, LABEL_0..2, star ratings); unknown labels map to neutral.
_POSITIVE_LABELS = {"positive", "pos", "label_2", "bullish", "5 stars", "4 stars"}
_NEGATIVE_LABELS = {"negative", "neg", "label_0", "bearish", "1 star", "2 stars"}


class HuggingFaceClient(ExternalApiClient):
    def __init__(
        self,
        cfg: Settings | None = None,
        *,
        client: httpx.Client | None = None,
        **kwargs: Any,
    ) -> None:
        cfg = cfg or default_settings
        self._model = cfg.huggingface_model
        super().__init__(
            provider=PROVIDER,
            base_url=cfg.huggingface_base_url,
            # HF expects "Authorization: Bearer <token>".
            api_key=f"Bearer {cfg.huggingface_api_key}" if cfg.huggingface_api_key else "",
            auth_header="Authorization",
            rate_limit_per_minute=cfg.huggingface_rate_limit_per_minute,
            client=client,
            **kwargs,
        )

    def classify(self, text: str) -> list[dict[str, Any]]:
        """Return the model's raw ``[{label, score}, ...]`` list for one text.

        The HF inference API nests single-input results one level deep
        (``[[{...}]]``); this flattens to the inner list.
        """
        data = self.post_json(
            f"/models/{self._model}",
            json={"inputs": text[:512], "options": {"wait_for_model": True}},
        )
        if isinstance(data, list) and data and isinstance(data[0], list):
            return data[0]
        if isinstance(data, list):
            return data
        return []


class HuggingFaceSentimentBackend:
    """Adapter exposing the ``SentimentAnalyzer`` backend protocol over HF."""

    backend_name = "huggingface"

    def __init__(
        self,
        cfg: Settings | None = None,
        *,
        client: HuggingFaceClient | None = None,
    ) -> None:
        cfg = cfg or default_settings
        self.model_version = cfg.huggingface_model
        self._client = client or HuggingFaceClient(cfg)

    def score(self, text: str) -> SentimentBackendResult:
        results = self._client.classify(text)
        if not results:
            return SentimentBackendResult(0.5, 0.0, self.backend_name, self.model_version)

        # Pick the highest-scoring label and map it to a 0-1 bullishness score.
        top = max(results, key=lambda r: float(r.get("score", 0.0)))
        label = str(top.get("label", "")).lower()
        conf = max(0.0, min(1.0, float(top.get("score", 0.0))))

        if label in _POSITIVE_LABELS or "pos" in label:
            score = 0.5 + 0.5 * conf
        elif label in _NEGATIVE_LABELS or "neg" in label:
            score = 0.5 - 0.5 * conf
        else:
            score = 0.5  # neutral / unknown label
            conf = conf if label else 0.0

        return SentimentBackendResult(
            score=round(score, 4),
            confidence=round(conf, 4),
            backend=self.backend_name,
            model_version=self.model_version,
        )
