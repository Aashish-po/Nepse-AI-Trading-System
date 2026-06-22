"""News-sentiment aggregation + feature-builder tests (offline lexicon backend)."""

from __future__ import annotations

from datetime import date

import sqlalchemy as sa
from app.models.news import NewsArticle, NewsMention, SentimentRun
from app.services.external_features import NewsSentimentFeatureBuilder
from app.services.external_sentiment import (
    NEUTRAL_SCORE,
    SentimentRunService,
    aggregate_symbol_sentiment,
)


def _add_article(session, symbol: str, title: str, published: date | None) -> None:
    article = NewsArticle(
        provider="newsapi",
        url=f"https://news.test/{title}".replace(" ", "-"),
        url_hash=title,  # unique-enough for tests
        title=title,
        source="Wire",
        published_date=published,
    )
    session.add(article)
    session.flush()
    session.add(NewsMention(article_id=article.id, symbol=symbol.upper()))
    session.flush()


def test_no_articles_is_neutral_zero_confidence(db_session) -> None:
    agg = aggregate_symbol_sentiment(db_session, "NABIL", date(2024, 6, 10))
    assert agg["score"] == NEUTRAL_SCORE
    assert agg["confidence"] == 0.0
    assert agg["count"] == 0


def test_positive_news_scores_above_neutral(db_session) -> None:
    _add_article(
        db_session, "NABIL", "profit surges record growth strong upgrade", date(2024, 6, 5)
    )
    agg = aggregate_symbol_sentiment(db_session, "NABIL", date(2024, 6, 10), min_confidence=0.0)
    assert agg["count"] == 1
    assert agg["score"] > NEUTRAL_SCORE


def test_point_in_time_excludes_future_and_out_of_window(db_session) -> None:
    # In-window positive, plus a FUTURE article that must not leak in.
    _add_article(db_session, "NABIL", "profit surges strong", date(2024, 6, 5))
    _add_article(db_session, "NABIL", "loss decline weak", date(2024, 6, 20))  # future vs as_of
    _add_article(db_session, "NABIL", "old loss decline", date(2024, 1, 1))  # outside 7d window
    agg = aggregate_symbol_sentiment(db_session, "NABIL", date(2024, 6, 10), min_confidence=0.0)
    assert agg["count"] == 1  # only the Jun 5 article qualifies


def test_null_published_date_excluded(db_session) -> None:
    _add_article(db_session, "NABIL", "profit surges strong", None)
    agg = aggregate_symbol_sentiment(db_session, "NABIL", date(2024, 6, 10))
    assert agg["count"] == 0


def test_low_confidence_collapses_to_neutral(db_session) -> None:
    _add_article(db_session, "NABIL", "the market opened today", date(2024, 6, 5))
    # A neutral headline yields low confidence -> score forced to neutral.
    agg = aggregate_symbol_sentiment(db_session, "NABIL", date(2024, 6, 10), min_confidence=0.99)
    assert agg["score"] == NEUTRAL_SCORE


def test_run_service_persists_sentiment_run(db_session) -> None:
    _add_article(db_session, "NABIL", "profit surges strong upgrade", date(2024, 6, 5))
    svc = SentimentRunService(session=db_session, min_confidence=0.0)
    result = svc.run(["NABIL"], as_of=date(2024, 6, 10))
    assert result["status"] == "success"
    run = db_session.scalar(sa.select(SentimentRun).where(SentimentRun.symbol == "NABIL"))
    assert run is not None and run.count == 1 and run.score > NEUTRAL_SCORE
    # Re-run updates in place (idempotent on provider/symbol/date).
    svc.run(["NABIL"], as_of=date(2024, 6, 10))
    assert db_session.scalar(sa.select(sa.func.count()).select_from(SentimentRun)) == 1


def test_feature_builder_emits_registered_features(db_session) -> None:
    _add_article(db_session, "NABIL", "profit surges strong upgrade", date(2024, 6, 5))
    feats = NewsSentimentFeatureBuilder(session=db_session).build_features(
        "NABIL", date(2024, 6, 10)
    )
    assert set(feats["values"]) == {
        "news_sentiment_score_7d",
        "news_sentiment_confidence_7d",
        "news_article_count_7d",
    }
    assert feats["values"]["news_article_count_7d"] == 1.0
    assert feats["meta"]["news_window_days"] == 7
