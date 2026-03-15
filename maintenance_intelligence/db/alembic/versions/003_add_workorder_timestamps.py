"""add first-class workorder lifecycle timestamps

Revision ID: 003_add_workorder_timestamps
Revises: 002_pm_proposals
Create Date: 2026-03-15 20:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '003_add_workorder_timestamps'
down_revision: Union[str, None] = '002_pm_proposals'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


WORKORDER_TABLE = 'workorders'
COLUMNS = (
    ('workorder_created_at', sa.DateTime(timezone=True)),
    ('handoff_completed_at', sa.DateTime(timezone=True)),
    ('workorder_completed_at', sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    for column_name, column_type in COLUMNS:
        op.add_column(WORKORDER_TABLE, sa.Column(column_name, column_type, nullable=True))

    # Safe backfill outline only:
    # - workorder_created_at can later be backfilled from metadata->>'created_at' when present.
    # - handoff_completed_at can later be backfilled from PM approval / connector success timestamps.
    # - workorder_completed_at can later be backfilled from terminal CMMS response timestamps
    #   such as actfinish, statusdate, or changedate when those mappings are deterministic.


def downgrade() -> None:
    for column_name, _column_type in reversed(COLUMNS):
        op.drop_column(WORKORDER_TABLE, column_name)
