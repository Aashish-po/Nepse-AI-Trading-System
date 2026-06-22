"""News articles, symbol mentions, and aggregated sentiment runs.

``NewsArticle.url_hash`` (sha256 of the canonical URL) is unique so re-fetching
the same article is idempotent. ``SentimentRun`` stores aggregated per-symbol,
per-date sentiment derived from articles (and optional HF enrichment), unique on
``(provider, symbol, date)``.
"""

from __future__ import annotations

import datetime

from app.db.base import Base
from app.models.types import big_int_pk_type, json_dict_type
from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship


class NewsArticle(Base):
    __tablename__ = "news_articles"
    __table_args__ = (
        UniqueConstraint("url_hash", name="uq_news_articles_url_hash"),
        Index("ix_news_articles_published_date", "published_date"),
    )

    id: Mapped[int] = mapped_column(big_int_pk_type, primary_key=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    url_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    fetched_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_json: Mapped[dict | None] = mapped_column(json_dict_type, nullable=True)

    mentions: Mapped[list[NewsMention]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )


class NewsMention(Base):
    __tablename__ = "news_mentions"
    __table_args__ = (
        UniqueConstraint("article_id", "symbol", name="uq_news_mentions_article_symbol"),
        Index("ix_news_mentions_symbol", "symbol"),
    )

    id: Mapped[int] = mapped_column(big_int_pk_type, primary_key=True)
    article_id: Mapped[int] = mapped_column(
        big_int_pk_type, ForeignKey("news_articles.id", ondelete="CASCADE"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)

    article: Mapped[NewsArticle] = relationship(back_populates="mentions")


class SentimentRun(Base):
    __tablename__ = "sentiment_runs"
    __table_args__ = (
        UniqueConstraint(
            "provider", "symbol", "date", name="uq_sentiment_runs_provider_symbol_date"
        ),
    )

    id: Mapped[int] = mapped_column(big_int_pk_type, primary_key=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    symbol: Mapped[str | None] = mapped_column(String(20), nullable=True)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    features_json: Mapped[dict | None] = mapped_column(json_dict_type, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
