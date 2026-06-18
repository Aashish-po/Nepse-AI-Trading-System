"""Multilingual sentiment analysis pipeline (Phase 8).

This module provides an XLM-R based sentiment pipeline for scoring financial
news and social text, with a dependency-free lexicon backend used as the
default fallback. The lexicon backend keeps the pipeline fully offline and
testable while the optional transformer backend (``xlm-roberta``) is loaded
lazily only when ``transformers``/``torch`` and a fine-tuned model are
available.

Output contract (consumed by the Signal Fusion Engine, Phase 9):

    {
        "sentiment": "bullish" | "bearish" | "neutral",
        "score": 0.0-1.0,        # 0 = very bearish, 0.5 = neutral, 1 = very bullish
        "confidence": 0.0-1.0,
        "backend": "lexicon" | "xlm-roberta",
        "model_version": str,
    }

``score`` deliberately matches the ``sentiment_signal["score"]`` shape expected
by :class:`backend.app.services.signal_fusion.SignalFusionEngine`.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

LEXICON_VERSION = "lexicon-v1"
XLMR_DEFAULT_MODEL = "xlm-roberta-base"

# Polarity lexicon spanning English and (romanized + Devanagari) Nepali finance
# vocabulary. Values are in [-1.0, 1.0]; magnitude encodes intensity. This is a
# pragmatic stand-in for a fine-tuned XLM-R head and is intentionally compact
# and auditable rather than exhaustive.
SENTIMENT_LEXICON: dict[str, float] = {
    # --- English bullish ---
    "gain": 0.6,
    "gains": 0.6,
    "surge": 0.9,
    "surged": 0.9,
    "soar": 0.9,
    "soared": 0.9,
    "rally": 0.8,
    "rallied": 0.8,
    "rise": 0.5,
    "rises": 0.5,
    "rising": 0.5,
    "rose": 0.5,
    "up": 0.4,
    "upbeat": 0.6,
    "bullish": 0.9,
    "growth": 0.6,
    "profit": 0.7,
    "profits": 0.7,
    "profitable": 0.7,
    "record": 0.5,
    "beat": 0.6,
    "beats": 0.6,
    "outperform": 0.7,
    "strong": 0.6,
    "stronger": 0.6,
    "boost": 0.6,
    "boosted": 0.6,
    "dividend": 0.5,
    "bonus": 0.5,
    "recovery": 0.6,
    "recover": 0.5,
    "optimistic": 0.7,
    "positive": 0.6,
    "buy": 0.6,
    "upgrade": 0.7,
    "upgraded": 0.7,
    "expansion": 0.5,
    # --- English bearish ---
    "loss": -0.7,
    "losses": -0.7,
    "fall": -0.5,
    "falls": -0.5,
    "falling": -0.5,
    "fell": -0.5,
    "drop": -0.6,
    "dropped": -0.6,
    "plunge": -0.9,
    "plunged": -0.9,
    "crash": -0.95,
    "crashed": -0.95,
    "slump": -0.8,
    "slumped": -0.8,
    "decline": -0.6,
    "declined": -0.6,
    "down": -0.4,
    "downbeat": -0.6,
    "bearish": -0.9,
    "weak": -0.6,
    "weaker": -0.6,
    "miss": -0.6,
    "missed": -0.6,
    "underperform": -0.7,
    "negative": -0.6,
    "sell": -0.6,
    "selloff": -0.8,
    "downgrade": -0.7,
    "downgraded": -0.7,
    "fraud": -0.95,
    "scam": -0.95,
    "default": -0.8,
    "bankruptcy": -0.95,
    "pessimistic": -0.7,
    "warning": -0.5,
    "risk": -0.3,
    "concern": -0.4,
    "concerns": -0.4,
    "fear": -0.6,
    "fears": -0.6,
    # --- Romanized Nepali ---
    "badhyo": 0.7,  # increased
    "badhdo": 0.6,
    "naafa": 0.7,  # profit
    "munafa": 0.7,
    "tejī": 0.8,
    "teji": 0.8,  # bullish/uptrend
    "ghatyo": -0.7,  # decreased
    "ghatdo": -0.6,
    "noksan": -0.7,  # loss
    "ghata": -0.6,
    "mandi": -0.8,  # bearish/downtrend
    "girawat": -0.7,  # decline
    # --- Devanagari Nepali ---
    "बढ्यो": 0.7,
    "नाफा": 0.7,
    "मुनाफा": 0.7,
    "तेजी": 0.8,
    "घट्यो": -0.7,
    "नोक्सान": -0.7,
    "घाटा": -0.6,
    "मन्दी": -0.8,
    "गिरावट": -0.7,
}

# Words that flip the polarity of the following token.
NEGATIONS: frozenset[str] = frozenset(
    {"no", "not", "never", "without", "lack", "lacks", "na", "chaina", "छैन"}
)

# A word is a base letter followed by any run of letters or combining marks.
# Devanagari vowel signs (matras), the virama, and other diacritics are Unicode
# *marks* (category M), which ``\w`` excludes -- without listing them here the
# tokenizer would split "नाफा" into ["न", "फ"] and the Devanagari lexicon would
# never match. Range covers the Devanagari combining marks: signs (U+0900-0903),
# nukta (U+093C), matras + virama (U+093E-094F), and vedic/vocalic extensions.
_LETTER = r"[^\W\d_]"
_MARK = "[ऀ-ः़ा-ॏ॑-ॗॢॣ]"
_WORD_RE = re.compile(rf"{_LETTER}(?:{_LETTER}|{_MARK})*", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    """Lowercase word tokenizer that keeps Unicode (Devanagari) letters and
    their combining marks together as single tokens."""
    return [tok.lower() for tok in _WORD_RE.findall(text or "")]


def _label_from_score(score: float, neutral_band: float = 0.1) -> str:
    """Map a 0-1 score to a sentiment label around the 0.5 neutral midpoint."""
    if score >= 0.5 + neutral_band:
        return "bullish"
    if score <= 0.5 - neutral_band:
        return "bearish"
    return "neutral"


@dataclass
class SentimentBackendResult:
    score: float  # 0-1, 0.5 = neutral
    confidence: float  # 0-1
    backend: str
    model_version: str


class LexiconSentimentBackend:
    """Deterministic, dependency-free multilingual lexicon scorer."""

    backend_name = "lexicon"
    model_version = LEXICON_VERSION

    def __init__(self, lexicon: dict[str, float] | None = None) -> None:
        self._lexicon = lexicon if lexicon is not None else SENTIMENT_LEXICON

    def score(self, text: str) -> SentimentBackendResult:
        tokens = _tokenize(text)
        polarities: list[float] = []
        negate = False
        for tok in tokens:
            if tok in NEGATIONS:
                negate = True
                continue
            polarity = self._lexicon.get(tok)
            if polarity is not None:
                polarities.append(-polarity if negate else polarity)
            negate = False

        if not polarities:
            # No sentiment-bearing tokens -> neutral, low confidence.
            return SentimentBackendResult(0.5, 0.0, self.backend_name, self.model_version)

        mean_polarity = sum(polarities) / len(polarities)  # [-1, 1]
        score = (mean_polarity + 1.0) / 2.0  # -> [0, 1]

        # Confidence grows with signal strength and the number of hits, so a
        # single weak word is less trustworthy than several strong ones.
        strength = min(abs(mean_polarity), 1.0)
        coverage = min(len(polarities) / 3.0, 1.0)
        confidence = round(strength * (0.5 + 0.5 * coverage), 4)

        return SentimentBackendResult(
            score=round(score, 4),
            confidence=confidence,
            backend=self.backend_name,
            model_version=self.model_version,
        )


class TransformerSentimentBackend:
    """Optional XLM-R backend. Loaded lazily; requires ``transformers``.

    Falls back to raising :class:`RuntimeError` when the dependency or model is
    unavailable so callers can degrade to the lexicon backend.
    """

    backend_name = "xlm-roberta"

    def __init__(self, model_name: str = XLMR_DEFAULT_MODEL, device: str = "cpu") -> None:
        self.model_version = model_name
        self._device = device
        self._pipe = None  # lazy

    def _ensure_loaded(self) -> None:
        if self._pipe is not None:
            return
        try:
            from transformers import pipeline  # type: ignore
        except Exception as exc:  # noqa: BLE001 - dependency optional
            raise RuntimeError("transformers is not installed; use the lexicon backend") from exc

        device = 0 if self._device.startswith("cuda") else -1
        self._pipe = pipeline(
            "sentiment-analysis",
            model=self.model_version,
            tokenizer=self.model_version,
            device=device,
        )

    def score(self, text: str) -> SentimentBackendResult:
        self._ensure_loaded()
        assert self._pipe is not None
        raw = self._pipe(text[:512])[0]  # truncate to model max length
        label = str(raw.get("label", "")).lower()
        model_conf = float(raw.get("score", 0.5))

        # Normalize common label schemes to a 0-1 bullishness score.
        if "pos" in label or label in {"label_2", "bullish", "5 stars", "4 stars"}:
            score = 0.5 + 0.5 * model_conf
        elif "neg" in label or label in {"label_0", "bearish", "1 star", "2 stars"}:
            score = 0.5 - 0.5 * model_conf
        else:
            score = 0.5

        return SentimentBackendResult(
            score=round(score, 4),
            confidence=round(model_conf, 4),
            backend=self.backend_name,
            model_version=self.model_version,
        )


class SentimentAnalyzer:
    """High-level multilingual sentiment pipeline.

    ``backend="auto"`` prefers the XLM-R transformer when available and
    transparently falls back to the lexicon backend otherwise.
    """

    def __init__(
        self,
        backend: str = "auto",
        model_name: str = XLMR_DEFAULT_MODEL,
        device: str = "cpu",
    ) -> None:
        self._lexicon = LexiconSentimentBackend()
        self._transformer: TransformerSentimentBackend | None = None
        self._mode = backend

        if backend in {"auto", "xlm-roberta", "transformer"}:
            try:
                self._transformer = TransformerSentimentBackend(model_name, device)
                # Probe availability without downloading on "auto".
                if backend != "auto":
                    self._transformer._ensure_loaded()
            except Exception as exc:  # noqa: BLE001
                if backend != "auto":
                    raise
                logger.info("XLM-R unavailable, using lexicon sentiment backend: %s", exc)
                self._transformer = None

    def _active_backend(self):
        if self._transformer is not None:
            return self._transformer
        return self._lexicon

    def analyze(self, text: str) -> dict:
        """Score a single text into the fusion-compatible output contract."""
        backend = self._active_backend()
        try:
            result = backend.score(text)
        except Exception as exc:  # noqa: BLE001 - transformer runtime failure
            logger.warning("Sentiment backend %s failed, using lexicon: %s", backend, exc)
            self._transformer = None
            result = self._lexicon.score(text)

        return {
            "sentiment": _label_from_score(result.score),
            "score": result.score,
            "confidence": result.confidence,
            "backend": result.backend,
            "model_version": result.model_version,
        }

    def analyze_batch(self, texts: list[str]) -> list[dict]:
        return [self.analyze(text) for text in texts]

    def aggregate(self, texts: list[str]) -> dict:
        """Confidence-weighted aggregate sentiment over many texts.

        Useful for collapsing a day's worth of headlines for one symbol into a
        single sentiment signal.
        """
        results = self.analyze_batch(texts)
        scored = [r for r in results if r["confidence"] > 0]
        if not scored:
            return {
                "sentiment": "neutral",
                "score": 0.5,
                "confidence": 0.0,
                "count": len(results),
                "backend": self._active_backend().backend_name,
            }

        total_w = sum(r["confidence"] for r in scored)
        agg_score = sum(r["score"] * r["confidence"] for r in scored) / total_w
        agg_conf = total_w / len(scored)
        return {
            "sentiment": _label_from_score(agg_score),
            "score": round(agg_score, 4),
            "confidence": round(min(agg_conf, 1.0), 4),
            "count": len(results),
            "backend": self._active_backend().backend_name,
        }

    @staticmethod
    def to_signal(result: dict, buy_threshold: float = 0.6, sell_threshold: float = 0.4) -> dict:
        """Map a sentiment result to a BUY/SELL/HOLD signal for fusion."""
        score = result.get("score", 0.5)
        if score >= buy_threshold:
            signal = "BUY"
        elif score <= sell_threshold:
            signal = "SELL"
        else:
            signal = "HOLD"
        return {
            "signal": signal,
            "confidence": result.get("confidence", 0.0),
            "score": score,
            "provider": "sentiment",
        }


class SymbolSentimentFetcher:
    """Fetch and score news sentiment for a specific symbol on a given date."""

    # Mapping of symbols to common news source keywords
    SYMBOL_KEYWORDS: dict[str, list[str]] = {
        "NABIL": ["nabil", "nabil bank", "nbl"],
        "SCB": ["standard chartered", "scb nepal"],
        "NTC": ["nepal telecom", "ntc", "nepal tele"],
        "NEPSE": ["nepse", "nepal stock exchange", "stock market"],
    }

    def __init__(self, backend: str = "auto") -> None:
        self._analyzer = SentimentAnalyzer(backend=backend)

    def compute(self, symbol: str, date_obj: date | None = None) -> dict[str, Any]:
        """
        Compute sentiment score for a symbol.

        Args:
            symbol: Stock symbol to analyze
            date_obj: Date to analyze (currently fetches recent news)

        Returns:
            {"sentiment": "bullish/bearish/neutral", "score": 0-1, "confidence": 0-1}
        """
        # Get keywords for this symbol
        keywords = self.SYMBOL_KEYWORDS.get(symbol.upper(), [symbol.lower()])

        # For now, use existing sentiment analyzer on mock data
        # In production, this would fetch real news from sharesansar.com, etc.
        mock_headlines = self._fetch_news_headlines(symbol, keywords, date_obj)

        if not mock_headlines:
            return {"sentiment": "neutral", "score": 0.5, "confidence": 0.0}

        # Aggregate sentiment across headlines
        return self._analyzer.aggregate(mock_headlines)

    def _fetch_news_headlines(
        self, symbol: str, keywords: list[str], date_obj: date | None = None
    ) -> list[str]:
        """
        Fetch news headlines for the symbol.

        Currently returns placeholder headlines. In production, implement:
        - Scrapes sharesansar.com news archive
        - Filters by symbol keywords
        - Returns headlines from the last 7 days
        """
        # Placeholder: In production, implement actual news scraping
        # Example: requests.get(f"https://www.sharesansar.com/category/news")
        # Then parse and filter by keywords
        return []


def sentiment_score_to_signal(score: float, confidence: float) -> dict[str, Any]:
    """Convert sentiment score to fusion-compatible signal format.

    Maps -1 (bearish) to 0..1 bullish score used by SignalFusionEngine.
    """
    # score is already 0-1 from SentimentAnalyzer
    if score >= 0.6:
        signal = "BUY"
        conf = confidence
    elif score <= 0.4:
        signal = "SELL"
        conf = confidence
    else:
        signal = "HOLD"
        conf = 0.5

    return {"signal": signal, "confidence": conf, "score": score, "provider": "sentiment"}
