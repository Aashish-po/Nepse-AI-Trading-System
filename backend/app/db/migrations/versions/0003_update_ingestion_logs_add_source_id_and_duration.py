"""update ingestion logs add source_id and duration

Revision ID: 0003_update_ingestion_logs_add_source_id_and_duration
Revises: 0002_add_data_sources_and_ingestion_logs
Create Date: 2026-06-05
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_update_ingestion_logs_add_source_id_and_duration"
down_revision = "0002_add_data_sources_and_ingestion_logs"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('ingestion_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('source_id', sa.UUID(), nullable=True))
        batch_op.add_column(sa.Column('duration', sa.Float(), nullable=True))
        batch_op.create_foreign_key('fk_ingestion_logs_source_id', 'data_sources', ['source_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint("fk_ingestion_logs_source_id", "ingestion_logs", type_="foreignkey")
    op.drop_column("ingestion_logs", "duration")
    op.drop_column("ingestion_logs", "source_id")
