"""Tests for the Phase 8 multilingual sentiment pipeline (``ml/sentiment.py``).

These exercise the deterministic, dependency-free lexicon backend so the suite
never requires ``transformers``/``torch`` or a network download. The
transformer (XLM-R) backend is only verified to degrade gracefully when its
dependency is unavailable.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ml.sentiment import (
    SENTIMENT_LEXICON,
    LexiconSentimentBackend,
    SentimentAnalyzer,
    TransformerSentimentBackend,
)


class TestLexiconBackend:
    def test_bullish_text_scores_above_neutral(self) -> None:
        backend = LexiconSentimentBackend()
        result = backend.score("Bank profits surged to a record high")
        assert result.score > 0.5
        assert result.confidence > 0.0
        assert result.backend == "lexicon"

    def test_bearish_text_scores_below_neutral(self) -> None:
        backend = LexiconSentimentBackend()
        result = backend.score("Shares crashed after a huge loss and fraud warning")
        assert result.score < 0.5
        assert result.confidence > 0.0

    def test_text_without_sentiment_words_is_neutral(self) -> None:
        backend = LexiconSentimentBackend()
        result = backend.score("The meeting is scheduled for Tuesday")
        assert result.score == 0.5
        assert result.confidence == 0.0

    def test_negation_flips_polarity(self) -> None:
        backend = LexiconSentimentBackend()
        positive = backend.score("profit")
        negated = backend.score("no profit")
        assert positive.score > 0.5
        assert negated.score < 0.5

    def test_romanized_nepali_is_scored(self) -> None:
        backend = LexiconSentimentBackend()
        assert backend.score("naafa badhyo").score > 0.5  # profit increased
        assert backend.score("noksan ghatyo").score < 0.5  # loss decreased

    def test_devanagari_nepali_is_scored(self) -> None:
        # Score the exact lexicon keys to avoid Unicode normalization drift
        # between this file and the module source.
        backend = LexiconSentimentBackend()
        bullish = next(
            word for word, pol in SENTIMENT_LEXICON.items() if pol > 0 and not word.isascii()
        )
        bearish = next(
            word for word, pol in SENTIMENT_LEXICON.items() if pol < 0 and not word.isascii()
        )
        assert backend.score(bullish).score > 0.5
        assert backend.score(bearish).score < 0.5

    def test_scores_are_bounded(self) -> None:
        backend = LexiconSentimentBackend()
        for text in ["surge rally soar profit", "crash plunge fraud bankruptcy", ""]:
            result = backend.score(text)
            assert 0.0 <= result.score <= 1.0
            assert 0.0 <= result.confidence <= 1.0


class TestSentimentAnalyzer:
    def test_lexicon_backend_is_default_when_transformer_unavailable(self) -> None:
        analyzer = SentimentAnalyzer(backend="auto")
        result = analyzer.analyze("Stocks rallied on strong earnings")
        assert result["sentiment"] == "bullish"
        assert result["backend"] == "lexicon"
        assert set(result) >= {"sentiment", "score", "confidence", "backend", "model_version"}

    def test_label_mapping_matches_score(self) -> None:
        analyzer = SentimentAnalyzer(backend="lexicon")
        assert analyzer.analyze("plunge crash fraud")["sentiment"] == "bearish"
        assert analyzer.analyze("The report was published")["sentiment"] == "neutral"

    def test_analyze_batch_returns_one_result_per_text(self) -> None:
        analyzer = SentimentAnalyzer(backend="lexicon")
        results = analyzer.analyze_batch(["profit surge", "loss crash", "neutral text here"])
        assert len(results) == 3
        assert results[0]["sentiment"] == "bullish"
        assert results[1]["sentiment"] == "bearish"

    def test_aggregate_is_confidence_weighted(self) -> None:
        analyzer = SentimentAnalyzer(backend="lexicon")
        agg = analyzer.aggregate(
            ["profits surged to record highs", "company beats estimates", "no news today"]
        )
        assert agg["sentiment"] == "bullish"
        assert agg["count"] == 3
        assert 0.0 <= agg["confidence"] <= 1.0

    def test_aggregate_with_no_signal_is_neutral(self) -> None:
        analyzer = SentimentAnalyzer(backend="lexicon")
        agg = analyzer.aggregate(["the meeting is on tuesday", "report filed"])
        assert agg["sentiment"] == "neutral"
        assert agg["score"] == 0.5
        assert agg["confidence"] == 0.0

    def test_to_signal_produces_fusion_compatible_shape(self) -> None:
        buy = SentimentAnalyzer.to_signal({"score": 0.8, "confidence": 0.7})
        sell = SentimentAnalyzer.to_signal({"score": 0.2, "confidence": 0.7})
        hold = SentimentAnalyzer.to_signal({"score": 0.5, "confidence": 0.1})
        assert buy["signal"] == "BUY"
        assert sell["signal"] == "SELL"
        assert hold["signal"] == "HOLD"
        for sig in (buy, sell, hold):
            assert set(sig) == {"signal", "confidence", "score", "provider"}
            assert sig["provider"] == "sentiment"


class TestTransformerBackendDegradation:
    def test_missing_transformers_raises_runtime_error(self) -> None:
        import importlib.util

        import pytest

        if importlib.util.find_spec("transformers") is not None:
            pytest.skip("transformers is installed; degradation path not exercised")

        # Dependency genuinely absent: loading must raise a clear error so the
        # analyzer can transparently fall back to the lexicon backend.
        backend = TransformerSentimentBackend()
        with pytest.raises(RuntimeError):
            backend.score("anything")
