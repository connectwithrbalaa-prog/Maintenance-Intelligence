ALTER TABLE workorders ADD COLUMN IF NOT EXISTS org_id TEXT;
ALTER TABLE doc_chunks ADD COLUMN IF NOT EXISTS org_id TEXT;

CREATE INDEX IF NOT EXISTS idx_workorders_org_asset ON workorders (org_id, asset_id);
CREATE INDEX IF NOT EXISTS idx_doc_chunks_org_asset ON doc_chunks (org_id, asset_id);