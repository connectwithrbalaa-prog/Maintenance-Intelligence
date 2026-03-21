"""add rca_feedback table

Revision ID: 005_rca_feedback
Revises: 004_events_occurred_at
Create Date: 2026-03-15 22:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "005_rca_feedback"
down_revision: Union[str, None] = "004_events_occurred_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rca_feedback",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("recommendation_id", sa.Text(), nullable=False),
        sa.Column("org_id", sa.Text(), nullable=True),
        sa.Column("asset_id", sa.Text(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("changes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("rca_feedback_run_idx", "rca_feedback", ["run_id"])
    op.create_index("rca_feedback_rec_idx", "rca_feedback", ["recommendation_id"])


def downgrade() -> None:
    op.drop_index("rca_feedback_rec_idx", table_name="rca_feedback")
    op.drop_index("rca_feedback_run_idx", table_name="rca_feedback")
    op.drop_table("rca_feedback")
