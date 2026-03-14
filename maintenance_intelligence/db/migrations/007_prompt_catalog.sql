CREATE TABLE IF NOT EXISTS prompt_catalog (
  prompt_id TEXT PRIMARY KEY,
  route_name TEXT NOT NULL,
  version INTEGER NOT NULL,
  description TEXT NOT NULL,
  intended_use JSONB,
  system_prompt TEXT NOT NULL,
  user_prompt_template TEXT NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS prompt_route_configs (
  config_id TEXT PRIMARY KEY,
  org_id TEXT,
  route_name TEXT NOT NULL,
  default_prompt_id TEXT NOT NULL,
  canary_prompt_id TEXT,
  canary_ratio FLOAT NOT NULL DEFAULT 0.0,
  auto_rollback_enabled BOOLEAN NOT NULL DEFAULT TRUE,
  rollback_min_runs INTEGER NOT NULL DEFAULT 20,
  rollback_acceptance_delta FLOAT NOT NULL DEFAULT 0.05,
  updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE rca_feedback ADD COLUMN IF NOT EXISTS prompt_id TEXT;
ALTER TABLE rca_feedback ADD COLUMN IF NOT EXISTS prompt_route TEXT;

CREATE INDEX IF NOT EXISTS idx_prompt_catalog_route_active ON prompt_catalog (route_name, active);
CREATE INDEX IF NOT EXISTS idx_prompt_configs_org_route ON prompt_route_configs (org_id, route_name);
CREATE INDEX IF NOT EXISTS idx_feedback_prompt ON rca_feedback (prompt_id, action);