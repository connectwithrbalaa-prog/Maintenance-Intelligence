"""Add org_id columns to signals and signal_rollups

Revision ID: 003_signals_org_scope
Revises: 002_multi_tenant_rbac
Create Date: 2026-03-14 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_signals_org_scope"
down_revision: Union[str, None] = "002_multi_tenant_rbac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("signals", sa.Column("org_id", sa.Text(), nullable=True))
    op.add_column("signal_rollups", sa.Column("org_id", sa.Text(), nullable=True))
    op.create_index("idx_signals_org_asset_time", "signals", ["org_id", "asset_id", "timestamp"], unique=False)
    op.create_index("idx_rollups_org_asset_end", "signal_rollups", ["org_id", "asset_id", "end_time"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_rollups_org_asset_end", table_name="signal_rollups")
    op.drop_index("idx_signals_org_asset_time", table_name="signals")
    op.drop_column("signal_rollups", "org_id")
    op.drop_column("signals", "org_id")