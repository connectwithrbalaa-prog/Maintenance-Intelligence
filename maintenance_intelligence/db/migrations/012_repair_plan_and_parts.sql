CREATE TABLE IF NOT EXISTS repair_plan (
    plan_id TEXT PRIMARY KEY,
    run_id TEXT,
    recommendation_id TEXT,
    org_id TEXT,
    asset_id TEXT,
    summary TEXT,
    rationale TEXT,
    confidence DOUBLE PRECISION,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_repair_plan_status_created_at
    ON repair_plan (status, created_at);

CREATE INDEX IF NOT EXISTS idx_repair_plan_asset_id
    ON repair_plan (asset_id);

CREATE TABLE IF NOT EXISTS repair_part (
    part_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES repair_plan(plan_id) ON DELETE CASCADE,
    name TEXT,
    description TEXT,
    quantity INTEGER,
    unit TEXT,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_repair_part_plan_id
    ON repair_part (plan_id);