CREATE TABLE IF NOT EXISTS pm_change_proposals (
  proposal_id TEXT PRIMARY KEY,
  org_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  recommendation_id TEXT NOT NULL,
  asset_id TEXT NOT NULL,
  proposal_title TEXT NOT NULL,
  proposal_summary TEXT NOT NULL,
  recommended_actions JSONB NOT NULL DEFAULT '[]'::jsonb,
  playbook_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
  status TEXT NOT NULL DEFAULT 'draft',
  approved_by TEXT,
  approved_at TIMESTAMPTZ,
  cms_reference TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pm_change_proposals_org_status
  ON pm_change_proposals (org_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_pm_change_proposals_recommendation
  ON pm_change_proposals (recommendation_id);

CREATE INDEX IF NOT EXISTS idx_pm_change_proposals_run
  ON pm_change_proposals (run_id);