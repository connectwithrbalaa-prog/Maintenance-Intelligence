-- Enable pgvector extension (safe if already exists)
CREATE EXTENSION IF NOT EXISTS vector;

-- Add embedding vector column to doc_chunks if missing
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_name = 'doc_chunks' AND column_name = 'embedding'
  ) THEN
    ALTER TABLE doc_chunks ADD COLUMN embedding vector(1536);
  END IF;
END $$;

-- Simple index (optional; improves ANN search later)
-- CREATE INDEX IF NOT EXISTS doc_chunks_embedding_idx ON doc_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
