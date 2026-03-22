"""Add tenant_id to workorders, signals, and signal_rollups for multi-tenancy.

Revision ID: 008_add_tenant_id_columns
Revises: 007_iso14224_canonical_model
Create Date: 2026-03-22 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "008_add_tenant_id_columns"
down_revision: Union[str, None] = "007_iso14224_canonical_model"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("workorders", sa.Column("tenant_id", sa.Text(), nullable=True))
    op.add_column("signals", sa.Column("tenant_id", sa.Text(), nullable=True))
    op.add_column("signal_rollups", sa.Column("tenant_id", sa.Text(), nullable=True))
    op.create_index("idx_workorders_tenant", "workorders", ["tenant_id"])
    op.create_index("idx_signals_tenant", "signals", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("idx_signals_tenant", table_name="signals")
    op.drop_index("idx_workorders_tenant", table_name="workorders")
    op.drop_column("signal_rollups", "tenant_id")
    op.drop_column("signals", "tenant_id")
    op.drop_column("workorders", "tenant_id")
