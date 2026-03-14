set -euo pipefail
BRANCH="feature/pgvector-rag"

git fetch origin
git checkout -b "$BRANCH" || git checkout "$BRANCH"

mkdir -p maintenance_intelligence/rag maintenance_intelligence/db/migrations

# Migration: enable pgvector + embedding column
cat > maintenance_intelligence/db/migrations/002_pgvector.sql << 'SQL'
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
SQL

# RAG ingestion (embeddings + chunk storage)
cat > maintenance_intelligence/rag/ingest.py << 'PY'
import os, json, uuid, pathlib, re, time
from typing import List, Dict, Any
import psycopg2
from loguru import logger
from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.context.assembler import with_pg

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

EMBED_MODEL = os.getenv("MI_EMBED_MODEL", "text-embedding-3-large")

def embed_texts(api_key: str, texts: List[str]) -> List[List[float]]:
    if OpenAI is None:
        raise RuntimeError("openai package not installed")
    client = OpenAI(api_key=api_key)
    # Batched embeddings (simple one-shot for MVP)
    resp = client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [d.embedding for d in resp.data]

def chunk_text(text: str, max_chars: int = 1200, overlap: int = 100) -> List[str]:
    chunks = []
    i = 0
    n = len(text)
    while i < n:
        j = min(i + max_chars, n)
        chunk = text[i:j]
        chunks.append(chunk)
        if j == n:
            break
        i = max(0, j - overlap)
    return [c.strip() for c in chunks if c.strip()]

def load_texts(path: str) -> List[Dict[str, Any]]:
    p = pathlib.Path(path)
    files = []
    if p.is_dir():
        for f in p.rglob("*"):
            if f.suffix.lower() in (".txt", ".md"):
                files.append(f)
    elif p.exists():
        files = [p]
    else:
        raise FileNotFoundError(path)
    docs = []
    for f in files:
        try:
            t = f.read_text(encoding="utf-8", errors="ignore")
            docs.append({"title": f.name, "content": t, "source": str(f)})
        except Exception as e:
            logger.warning({"event":"rag.read.skip","file":str(f),"err":str(e)})
    return docs

def upsert_chunks(conn, asset_id: str, docs: List[Dict[str, Any]], embeddings: List[List[float]], titles: List[str]):
    with conn:
        with conn.cursor() as cur:
            for i, doc in enumerate(docs):
                chunk_id = "DC-" + uuid.uuid4().hex[:12]
                cur.execute(
                    """
                    INSERT INTO doc_chunks (chunk_id, asset_id, title, content, source, embedding)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (chunk_id) DO NOTHING
                    """,
                    (chunk_id, asset_id, titles[i], doc["content"], doc["source"], embeddings[i]),
                )

def ingest_path(path: str, asset_id: str):
    s = Settings()
    conn = with_pg(s.pg_dsn)
    try:
        docs = load_texts(path)
        if not docs:
            logger.info({"event":"rag.empty","note":"No docs found"})
            return
        # simple chunking: each file -> 1 chunk; can switch to chunk_text per file if needed
        titles = [d["title"] for d in docs]
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.error({"event":"rag.no_api_key","note":"OPENAI_API_KEY not set"})
            return
        texts = [d["content"] for d in docs]
        embs = embed_texts(api_key, texts)
        upsert_chunks(conn, asset_id, docs, embs, titles)
        logger.info({"event":"rag.ingested","files":len(docs),"asset_id":asset_id})
    finally:
        conn.close()
PY

# CLI: add mi-rag ingest
python - << 'PY'
import os, io, sys
p = "maintenance_intelligence/runner/cli.py"
with open(p, "r", encoding="utf-8") as f:
    s = f.read()
if "def rag(" in s:
    sys.exit(0)
insert = '''
@app.command()
def rag(path: str, asset_id: str = typer.Option(..., help="Associate ingested chunks to this asset_id")):
    """
    Ingest docs into RAG store (doc_chunks with pgvector embeddings).
    Usage: mi-runner rag --path ./docs --asset-id PUMP-101
    """
    from maintenance_intelligence.rag.ingest import ingest_path
    ingest_path(path, asset_id)
'''
s = s.rstrip() + insert + "\\n"
with open(p, "w", encoding="utf-8") as f:
    f.write(s)
print("UPDATED", p)
PY

# Update assembler to try vector similarity (fallback to stub)
python - << 'PY'
import os, io, sys
p = "maintenance_intelligence/context/assembler.py"
with open(p, "r", encoding="utf-8") as f:
    s = f.read()
if "vector" in s and "embedding" in s and "cosine_distance" in s:
    sys.exit(0)
snippet = """
        # doc chunks via pgvector (if available)
        try:
            with conn, conn.cursor() as cur:
                # If pgvector/embedding not present, this will error and fall back
                cur.execute(
                    \"""
                    SELECT chunk_id, title
                    FROM doc_chunks
                    WHERE asset_id = %s
                    ORDER BY embedding <-> (SELECT embedding FROM doc_chunks WHERE asset_id = %s LIMIT 1)
                    LIMIT 3
                    \""",
                    (asset_id, asset_id)
                )
                rows = cur.fetchall()
                out["doc_chunks"] = [{"chunk_id": r[0], "title": r[1]} for r in rows if r]
        except Exception as e:
            # Keep prior stub/random fallback if vector unavailable
            pass
"""
# place before the previous stub doc selection; find 'doc_chunks stub' debug line and insert above or append if not found
anchor = "ctx.docs.skip"
if anchor in s:
    s = s.replace("logger.debug({\"event\":\"ctx.docs.skip\",\"err\":str(e)})", "logger.debug({\"event\":\"ctx.docs.skip\",\"err\":str(e)})" + snippet)
else:
    s += snippet
with open(p, "w", encoding="utf-8") as f:
    f.write(s)
print("UPDATED", p)
PY

# README additions
cat >> README.md << 'MD'

## Optional: pgvector RAG

- Enable extension + embedding column:
  - python -m maintenance_intelligence.db.migrate  (applies 002_pgvector.sql)
- Ingest docs:
  - mi-runner rag --path ./docs --asset-id PUMP-101
- Retrieval:
  - Context assembler tries vector similarity (pgvector) when available; falls back gracefully.

Notes:
- Requires OPENAI_API_KEY
- Embedding model can be set via MI_EMBED_MODEL (default: text-embedding-3-large)
MD

# Basic import test
cat > tests/test_rag_import.py << 'PY'
def test_rag_imports():
    from maintenance_intelligence.rag import ingest
    assert hasattr(ingest, "ingest_path")
PY

git add .
git commit -m "feat: optional pgvector RAG — migration, ingestion CLI (embeddings), and vector retrieval in assembler"
git push -u origin "$BRANCH"