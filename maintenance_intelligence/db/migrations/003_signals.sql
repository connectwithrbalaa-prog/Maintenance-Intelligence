-- signals table for time-series measurements and rollups
CREATE TABLE IF NOT EXISTS signals (
  signal_id TEXT PRIMARY KEY,
  org_id TEXT,
  asset_id TEXT,
  signal_type TEXT,  -- e.g., 'vibration', 'temperature'
  timestamp TIMESTAMPTZ,
  value FLOAT,
  unit TEXT,
  metadata JSONB,  -- source, event_id, etc.
  created_at TIMESTAMPTZ DEFAULT now()
);

-- rollups table for aggregated signals
CREATE TABLE IF NOT EXISTS signal_rollups (
  rollup_id TEXT PRIMARY KEY,
  org_id TEXT,
  asset_id TEXT,
  signal_type TEXT,
  period TEXT,  -- '1h', '6h', '24h'
  start_time TIMESTAMPTZ,
  end_time TIMESTAMPTZ,
  mean_value FLOAT,
  min_value FLOAT,
  max_value FLOAT,
  count INTEGER,
  anomaly_flags JSONB,  -- e.g., {"high_vibration": true, "spike": false}
  created_at TIMESTAMPTZ DEFAULT now()
);

-- indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_signals_asset_type_time ON signals (asset_id, signal_type, timestamp);
CREATE INDEX IF NOT EXISTS idx_rollups_asset_type_period ON signal_rollups (asset_id, signal_type, period, start_time DESC);
CREATE INDEX IF NOT EXISTS idx_signals_org_asset_time ON signals (org_id, asset_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_rollups_org_asset_end ON signal_rollups (org_id, asset_id, end_time DESC);