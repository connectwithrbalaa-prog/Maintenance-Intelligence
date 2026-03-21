"""add pm proposals table

Revision ID: 002_pm_proposals
Revises: 001_initial
Create Date: 2026-03-15 18:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002_pm_proposals"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pm_proposals",
        sa.Column("proposal_id", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=True),
        sa.Column("recommendation_id", sa.Text(), nullable=True),
        sa.Column("event_id", sa.Text(), nullable=True),
        sa.Column("asset_id", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("status", sa.Text(), nullable=True, server_default="pending"),
        sa.Column("source_file", sa.Text(), nullable=True),
        sa.Column("proposed_by", sa.Text(), nullable=True),
        sa.Column("approved_by", sa.Text(), nullable=True),
        sa.Column("work_order_id", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")
        ),
        sa.PrimaryKeyConstraint("proposal_id"),
    )
    op.create_index("idx_pm_proposals_status_created_at", "pm_proposals", ["status", "created_at"])
    op.create_index("idx_pm_proposals_asset_id", "pm_proposals", ["asset_id"])


def downgrade() -> None:
    op.drop_index("idx_pm_proposals_asset_id", table_name="pm_proposals")
    op.drop_index("idx_pm_proposals_status_created_at", table_name="pm_proposals")
    op.drop_table("pm_proposals")
