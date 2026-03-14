ALTER TABLE signals ADD COLUMN IF NOT EXISTS org_id TEXT;
ALTER TABLE signal_rollups ADD COLUMN IF NOT EXISTS org_id TEXT;

UPDATE signals
SET org_id = COALESCE(org_id, metadata->>'org_id', metadata->>'source_org_id')
WHERE org_id IS NULL;

UPDATE signal_rollups
SET org_id = COALESCE(org_id, anomaly_flags->>'org_id')
WHERE org_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_signals_org_asset_time ON signals (org_id, asset_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_rollups_org_asset_end ON signal_rollups (org_id, asset_id, end_time DESC);