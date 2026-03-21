"""rename events.event_time to occurred_at

Revision ID: 004_events_occurred_at
Revises: 003_add_workorder_timestamps
Create Date: 2026-03-15 22:10:00.000000
"""

from typing import Sequence, Union

from alembic import op

revision: str = "004_events_occurred_at"
down_revision: Union[str, None] = "003_add_workorder_timestamps"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'events'
                  AND column_name = 'event_time'
            ) AND NOT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'events'
                  AND column_name = 'occurred_at'
            ) THEN
                ALTER TABLE events RENAME COLUMN event_time TO occurred_at;
            END IF;
        END $$;
        """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'events'
                  AND column_name = 'occurred_at'
            ) AND NOT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'events'
                  AND column_name = 'event_time'
            ) THEN
                ALTER TABLE events RENAME COLUMN occurred_at TO event_time;
            END IF;
        END $$;
        """)
