"""Add prompt catalog, route config, and feedback prompt tracking

Revision ID: 004_prompt_catalog
Revises: 003_signals_org_scope
Create Date: 2026-03-14 12:15:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004_prompt_catalog"
down_revision: Union[str, None] = "003_signals_org_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "prompt_catalog",
        sa.Column("prompt_id", sa.Text(), nullable=False),
        sa.Column("route_name", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("intended_use", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("user_prompt_template", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")
        ),
        sa.PrimaryKeyConstraint("prompt_id"),
    )
    op.create_table(
        "prompt_route_configs",
        sa.Column("config_id", sa.Text(), nullable=False),
        sa.Column("org_id", sa.Text(), nullable=True),
        sa.Column("route_name", sa.Text(), nullable=False),
        sa.Column("default_prompt_id", sa.Text(), nullable=False),
        sa.Column("canary_prompt_id", sa.Text(), nullable=True),
        sa.Column("canary_ratio", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "auto_rollback_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("rollback_min_runs", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("rollback_acceptance_delta", sa.Float(), nullable=False, server_default="0.05"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")
        ),
        sa.PrimaryKeyConstraint("config_id"),
    )
    op.add_column("rca_feedback", sa.Column("prompt_id", sa.Text(), nullable=True))
    op.add_column("rca_feedback", sa.Column("prompt_route", sa.Text(), nullable=True))
    op.create_index(
        "idx_prompt_catalog_route_active", "prompt_catalog", ["route_name", "active"], unique=False
    )
    op.create_index(
        "idx_prompt_configs_org_route",
        "prompt_route_configs",
        ["org_id", "route_name"],
        unique=False,
    )
    op.create_index("idx_feedback_prompt", "rca_feedback", ["prompt_id", "action"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_feedback_prompt", table_name="rca_feedback")
    op.drop_index("idx_prompt_configs_org_route", table_name="prompt_route_configs")
    op.drop_index("idx_prompt_catalog_route_active", table_name="prompt_catalog")
    op.drop_column("rca_feedback", "prompt_route")
    op.drop_column("rca_feedback", "prompt_id")
    op.drop_table("prompt_route_configs")
    op.drop_table("prompt_catalog")
