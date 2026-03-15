CREATE TABLE IF NOT EXISTS pm_proposals (
  proposal_id TEXT PRIMARY KEY,
  run_id TEXT,
  recommendation_id TEXT,
  event_id TEXT,
  asset_id TEXT,
  title TEXT,
  rationale TEXT,
  confidence FLOAT,
  status TEXT DEFAULT 'pending',
  source_file TEXT,
  proposed_by TEXT,
  approved_by TEXT,
  work_order_id TEXT,
  metadata JSONB,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pm_proposals_status_created_at ON pm_proposals (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pm_proposals_asset_id ON pm_proposals (asset_id);