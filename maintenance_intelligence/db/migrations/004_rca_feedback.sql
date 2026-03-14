CREATE TABLE IF NOT EXISTS rca_feedback (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  recommendation_id TEXT NOT NULL,
  org_id TEXT,
  asset_id TEXT,
  action TEXT NOT NULL,          -- accept | reject | edited
  changes JSONB,                 -- fields changed (title/rationale/actions/etc.)
  reason TEXT,                   -- free-form reason/comment
  user_id TEXT,                  -- optional operator id
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS rca_feedback_run_idx ON rca_feedback (run_id);
CREATE INDEX IF NOT EXISTS rca_feedback_rec_idx ON rca_feedback (recommendation_id);