"""Add proposer subject to PM change proposals

Revision ID: 006_pm_change_proposals_identity
Revises: 005_pm_change_proposals
Create Date: 2026-03-14 23:10:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006_pm_change_proposals_identity"
down_revision: Union[str, None] = "005_pm_change_proposals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pm_change_proposals", sa.Column("proposer_subject", sa.Text(), nullable=True))
    op.create_index(
        "idx_pm_change_proposals_proposer_subject",
        "pm_change_proposals",
        ["proposer_subject"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_pm_change_proposals_proposer_subject", table_name="pm_change_proposals")
    op.drop_column("pm_change_proposals", "proposer_subject")