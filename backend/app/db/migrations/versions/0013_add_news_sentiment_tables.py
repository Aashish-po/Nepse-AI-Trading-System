"""Add news_articles, news_mentions, sentiment_runs tables

Revision ID: 0013_add_news_sentiment_tables
Revises: 0012_add_macro_tables
Create Date: 2026-06-22

"""

import sqlalchemy as sa
from alembic import op

revision = "0013_add_news_sentiment_tables"
down_revision = "0012_add_macro_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "news_articles",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("url_hash", sa.String(length=64), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=255), nullable=True),
        sa.Column("published_date", sa.Date(), nullable=True),
        sa.Column(
            "fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("raw_json", sa.JSON(), nullable=True),
        sa.UniqueConstraint("url_hash", name="uq_news_articles_url_hash"),
    )
    op.create_index("ix_news_articles_published_date", "news_articles", ["published_date"])

    op.create_table(
        "news_mentions",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True),
        sa.Column(
            "article_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            sa.ForeignKey("news_articles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.UniqueConstraint("article_id", "symbol", name="uq_news_mentions_article_symbol"),
    )
    op.create_index("ix_news_mentions_symbol", "news_mentions", ["symbol"])

    op.create_table(
        "sentiment_runs",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("symbol", sa.String(length=20), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("features_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "provider", "symbol", "date", name="uq_sentiment_runs_provider_symbol_date"
        ),
    )
    op.create_index("ix_sentiment_runs_symbol_date", "sentiment_runs", ["symbol", "date"])


def downgrade() -> None:
    op.drop_index("ix_sentiment_runs_symbol_date", table_name="sentiment_runs")
    op.drop_table("sentiment_runs")
    op.drop_index("ix_news_mentions_symbol", table_name="news_mentions")
    op.drop_table("news_mentions")
    op.drop_index("ix_news_articles_published_date", table_name="news_articles")
    op.drop_table("news_articles")
