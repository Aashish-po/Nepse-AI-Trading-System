"""Lightweight alternative-data sentiment helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class NewsSentiment:
    source: str
    symbol: str | None
    headline: str
    sentiment_score: float
    confidence: float
    published_at: datetime


class NewsSentimentService:
    """Deterministic sentiment helper used for tests and offline operation."""

    positive_words = ("beat", "growth", "profit", "surge", "record", "upgrade", "strong")
    negative_words = ("loss", "drop", "decline", "downgrade", "weak", "risk", "fall")

    def score_headline(self, headline: str) -> float:
        text = headline.lower()
        score = 0.5
        score += 0.1 * sum(word in text for word in self.positive_words)
        score -= 0.1 * sum(word in text for word in self.negative_words)
        return max(0.0, min(1.0, score))

    def adjust_confidence(self, base_confidence: float, sentiment_score: float) -> float:
        adjusted = base_confidence * (0.5 + sentiment_score / 2)
        return max(0.0, min(1.0, adjusted))
