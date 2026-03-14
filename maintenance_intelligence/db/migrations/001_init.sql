-- events table
CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY,
  event_time TIMESTAMPTZ,
  org_id TEXT,
  asset_id TEXT,
  kind TEXT,
  severity TEXT,
  summary TEXT,
  details JSONB,
  lineage JSONB
);

-- workorders table
CREATE TABLE IF NOT EXISTS workorders (
  wo_id TEXT PRIMARY KEY,
  asset_id TEXT,
  status TEXT,
  title TEXT,
  description TEXT,
  priority TEXT,
  metadata JSONB
);

-- optional doc_chunks stub for RAG
CREATE TABLE IF NOT EXISTS doc_chunks (
  chunk_id TEXT PRIMARY KEY,
  asset_id TEXT,
  title TEXT,
  content TEXT,
  source TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);
