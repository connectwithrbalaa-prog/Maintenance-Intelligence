"""Add org_id columns for multi-tenant workorders and doc chunks

Revision ID: 002_multi_tenant_rbac
Revises: 001_initial
Create Date: 2026-03-14 11:45:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_multi_tenant_rbac"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("workorders", sa.Column("org_id", sa.Text(), nullable=True))
    op.add_column("doc_chunks", sa.Column("org_id", sa.Text(), nullable=True))
    op.create_index("idx_workorders_org_asset", "workorders", ["org_id", "asset_id"], unique=False)
    op.create_index("idx_doc_chunks_org_asset", "doc_chunks", ["org_id", "asset_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_doc_chunks_org_asset", table_name="doc_chunks")
    op.drop_index("idx_workorders_org_asset", table_name="workorders")
    op.drop_column("doc_chunks", "org_id")
    op.drop_column("workorders", "org_id")