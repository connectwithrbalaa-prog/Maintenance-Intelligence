"""Initial migration - create all tables

Revision ID: 001_initial
Revises:
Create Date: 2024-01-15 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # events table
    op.create_table(
        "events",
        sa.Column("event_id", sa.Text(), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("org_id", sa.Text(), nullable=True),
        sa.Column("asset_id", sa.Text(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=True),
        sa.Column("severity", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("lineage", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("event_id"),
    )

    # workorders table
    op.create_table(
        "workorders",
        sa.Column("wo_id", sa.Text(), nullable=False),
        sa.Column("asset_id", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("priority", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("wo_id"),
    )

    # doc_chunks table
    op.create_table(
        "doc_chunks",
        sa.Column("chunk_id", sa.Text(), nullable=False),
        sa.Column("asset_id", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True
        ),
        sa.PrimaryKeyConstraint("chunk_id"),
    )

    # Add embedding column to doc_chunks
    op.add_column("doc_chunks", sa.Column("embedding", postgresql.VECTOR(1536), nullable=True))

    # Create IVFFlat index
    op.create_index(
        "doc_chunks_embedding_idx",
        "doc_chunks",
        ["embedding"],
        postgresql_using="ivfflat",
        postgresql_with={"lists": 100},
    )

    # signals table
    op.create_table(
        "signals",
        sa.Column("signal_id", sa.Text(), nullable=False),
        sa.Column("asset_id", sa.Text(), nullable=True),
        sa.Column("signal_type", sa.Text(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("unit", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True
        ),
        sa.PrimaryKeyConstraint("signal_id"),
    )

    # signal_rollups table
    op.create_table(
        "signal_rollups",
        sa.Column("rollup_id", sa.Text(), nullable=False),
        sa.Column("asset_id", sa.Text(), nullable=True),
        sa.Column("signal_type", sa.Text(), nullable=True),
        sa.Column("period", sa.Text(), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mean_value", sa.Float(), nullable=True),
        sa.Column("min_value", sa.Float(), nullable=True),
        sa.Column("max_value", sa.Float(), nullable=True),
        sa.Column("count", sa.Integer(), nullable=True),
        sa.Column("anomaly_flags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True
        ),
        sa.PrimaryKeyConstraint("rollup_id"),
    )

    # Indexes
    op.create_index(
        "idx_signals_asset_type_time", "signals", ["asset_id", "signal_type", "timestamp"]
    )
    op.create_index(
        "idx_rollups_asset_type_period",
        "signal_rollups",
        ["asset_id", "signal_type", "period", "start_time"],
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index("idx_rollups_asset_type_period", table_name="signal_rollups")
    op.drop_index("idx_signals_asset_type_time", table_name="signals")
    op.drop_index("doc_chunks_embedding_idx", table_name="doc_chunks")

    # Drop tables
    op.drop_table("signal_rollups")
    op.drop_table("signals")
    op.drop_table("doc_chunks")
    op.drop_table("workorders")
    op.drop_table("events")

    # Drop extension (optional)
    op.execute("DROP EXTENSION IF EXISTS vector")
