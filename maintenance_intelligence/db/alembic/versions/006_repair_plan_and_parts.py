"""add repair_plan and parts tables

Revision ID: 006_repair_plan_and_parts
Revises: 005_rca_feedback
Create Date: 2026-03-17 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "006_repair_plan_and_parts"
down_revision: Union[str, None] = "005_rca_feedback"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "repair_plan",
        sa.Column("plan_id", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=True),
        sa.Column("recommendation_id", sa.Text(), nullable=True),
        sa.Column("org_id", sa.Text(), nullable=True),
        sa.Column("asset_id", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("status", sa.Text(), nullable=True, server_default="pending"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")
        ),
        sa.PrimaryKeyConstraint("plan_id"),
    )
    op.create_index("idx_repair_plan_status_created_at", "repair_plan", ["status", "created_at"])
    op.create_index("idx_repair_plan_asset_id", "repair_plan", ["asset_id"])

    op.create_table(
        "repair_part",
        sa.Column("part_id", sa.Text(), nullable=False),
        sa.Column("plan_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("unit", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")
        ),
        sa.PrimaryKeyConstraint("part_id"),
        sa.ForeignKeyConstraint(["plan_id"], ["repair_plan.plan_id"], ondelete="CASCADE"),
    )
    op.create_index("idx_repair_part_plan_id", "repair_part", ["plan_id"])


def downgrade() -> None:
    op.drop_index("idx_repair_part_plan_id", table_name="repair_part")
    op.drop_table("repair_part")
    op.drop_index("idx_repair_plan_asset_id", table_name="repair_plan")
    op.drop_index("idx_repair_plan_status_created_at", table_name="repair_plan")
    op.drop_table("repair_plan")
