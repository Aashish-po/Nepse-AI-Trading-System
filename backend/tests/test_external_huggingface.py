"""Hugging Face client + sentiment-backend tests (offline, MockTransport)."""

from __future__ import annotations

import httpx
from app.core.config import Settings
from app.services.external.huggingface import HuggingFaceClient, HuggingFaceSentimentBackend
from app.services.external_sentiment import build_analyzer


def _cfg(enabled: bool = True) -> Settings:
    return Settings(  # type: ignore[call-arg]
        huggingface_enabled=enabled,
        huggingface_api_key="hf_key" if enabled else "",
        huggingface_model="test/model",
    )


def _client(handler) -> HuggingFaceClient:
    return HuggingFaceClient(_cfg(), client=httpx.Client(transport=httpx.MockTransport(handler)))


def _labels_handler(labels: list[dict], nested: bool = True):
    def handler(request: httpx.Request) -> httpx.Response:
        # HF inference auth header must be present and never empty.
        assert request.headers.get("Authorization", "").startswith("Bearer ")
        return httpx.Response(200, json=[labels] if nested else labels)

    return handler


def test_classify_flattens_nested_list() -> None:
    client = _client(_labels_handler([{"label": "POSITIVE", "score": 0.9}]))
    out = client.classify("profits up")
    assert out == [{"label": "POSITIVE", "score": 0.9}]


def test_backend_positive_label_maps_above_neutral() -> None:
    backend = HuggingFaceSentimentBackend(
        _cfg(), client=_client(_labels_handler([{"label": "POSITIVE", "score": 0.8}]))
    )
    result = backend.score("great earnings")
    assert result.score > 0.5
    assert 0.0 <= result.confidence <= 1.0
    assert result.backend == "huggingface"


def test_backend_negative_label_maps_below_neutral() -> None:
    backend = HuggingFaceSentimentBackend(
        _cfg(), client=_client(_labels_handler([{"label": "NEGATIVE", "score": 0.7}]))
    )
    assert backend.score("huge losses").score < 0.5


def test_backend_unknown_label_is_neutral() -> None:
    backend = HuggingFaceSentimentBackend(
        _cfg(), client=_client(_labels_handler([{"label": "WEATHER", "score": 0.6}]))
    )
    assert backend.score("something").score == 0.5


def test_build_analyzer_lexicon_when_disabled() -> None:
    analyzer = build_analyzer(_cfg(enabled=False))
    assert analyzer._active_backend().backend_name == "lexicon"


def test_build_analyzer_uses_hf_when_enabled(monkeypatch) -> None:
    # Force the injected HF backend to use a mocked transport.
    import app.services.external.huggingface as hf

    handler = _labels_handler([{"label": "POSITIVE", "score": 0.9}])

    class _StubBackend(HuggingFaceSentimentBackend):
        def __init__(self, cfg=None, *, client=None):  # type: ignore[no-untyped-def]
            super().__init__(_cfg(), client=_client(handler))

    monkeypatch.setattr(hf, "HuggingFaceSentimentBackend", _StubBackend)
    analyzer = build_analyzer(_cfg(enabled=True))
    assert analyzer._active_backend().backend_name == "huggingface"
    assert analyzer.analyze("profits soar")["backend"] == "huggingface"


def test_hf_failure_falls_back_to_lexicon() -> None:
    # A 500 from HF -> ExternalApiError inside score() -> analyzer degrades.
    def boom(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "down"})

    backend = HuggingFaceSentimentBackend(
        _cfg(),
        client=HuggingFaceClient(
            _cfg(),
            client=httpx.Client(transport=httpx.MockTransport(boom)),
            max_retries=1,
        ),
    )
    from ml.sentiment import SentimentAnalyzer

    analyzer = SentimentAnalyzer(backend="lexicon")
    analyzer._transformer = backend  # type: ignore[assignment]
    # "profit surges" is bullish in the lexicon -> proves lexicon ran after HF failed.
    result = analyzer.analyze("profit surges strong")
    assert result["backend"] == "lexicon"
    assert result["score"] > 0.5
