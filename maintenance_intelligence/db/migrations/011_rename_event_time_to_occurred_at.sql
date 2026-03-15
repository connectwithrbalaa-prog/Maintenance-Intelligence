-- Rename events.event_time to occurred_at to match ingestion and report queries.
-- Alembic remains the canonical migration path when available.

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
