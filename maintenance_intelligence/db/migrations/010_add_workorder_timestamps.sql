-- Add first-class lifecycle timestamps to workorders.
--
-- Alembic is the canonical path for this schema change when available.
-- This SQL file exists as a fallback for environments that still use raw SQL migrations.
--
-- Safe backfill outline only (do not run as part of this migration unless validated per environment):
--   1. workorder_created_at <- metadata->>'created_at'
--   2. handoff_completed_at <- persisted PM approval / connector success timestamp
--   3. workorder_completed_at <- metadata.response/raw_response terminal timestamps
--      such as actfinish, statusdate, or changedate

ALTER TABLE workorders
    ADD COLUMN IF NOT EXISTS workorder_created_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS handoff_completed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS workorder_completed_at TIMESTAMPTZ;
