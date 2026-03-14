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
