"""Add PM change proposal table

Revision ID: 005_pm_change_proposals
Revises: 004_prompt_catalog
Create Date: 2026-03-14 18:10:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005_pm_change_proposals"
down_revision: Union[str, None] = "004_prompt_catalog"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pm_change_proposals",
        sa.Column("proposal_id", sa.Text(), nullable=False),
        sa.Column("org_id", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("recommendation_id", sa.Text(), nullable=False),
        sa.Column("asset_id", sa.Text(), nullable=False),
        sa.Column("proposal_title", sa.Text(), nullable=False),
        sa.Column("proposal_summary", sa.Text(), nullable=False),
        sa.Column(
            "recommended_actions", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
            server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "playbook_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
            server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("approved_by", sa.Text(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cms_reference", sa.Text(), nullable=True),
        sa.Column(
            "metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
            server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.PrimaryKeyConstraint("proposal_id"),
    )
    op.create_index(
        "idx_pm_change_proposals_org_status",
        "pm_change_proposals",
        ["org_id", "status", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_pm_change_proposals_recommendation",
        "pm_change_proposals",
        ["recommendation_id"],
        unique=False,
    )
    op.create_index(
        "idx_pm_change_proposals_run",
        "pm_change_proposals",
        ["run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_pm_change_proposals_run", table_name="pm_change_proposals")
    op.drop_index("idx_pm_change_proposals_recommendation", table_name="pm_change_proposals")
    op.drop_index("idx_pm_change_proposals_org_status", table_name="pm_change_proposals")
    op.drop_table("pm_change_proposals")