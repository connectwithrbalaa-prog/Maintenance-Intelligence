import os
import pathlib
import re
import uuid
from typing import Any, Dict, List

from loguru import logger

from maintenance_intelligence.context.assembler import with_pg
from maintenance_intelligence.runner.config import Settings

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None

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

def extract_text_from_html(html_content: str) -> str:
    """Extract clean text from HTML."""
    if BeautifulSoup is None:
        # Fallback: remove tags with regex
        return re.sub(r'<[^>]+>', '', html_content).strip()
    soup = BeautifulSoup(html_content, 'html.parser')
    return soup.get_text(separator=' ', strip=True)

def load_texts(path: str) -> List[Dict[str, Any]]:
    p = pathlib.Path(path)
    files = []
    if p.is_dir():
        for f in p.rglob("*"):
            if f.suffix.lower() in (".txt", ".md", ".html", ".htm"):
                files.append(f)
    elif p.exists():
        files = [p]
    else:
        raise FileNotFoundError(path)
    docs = []
    for f in files:
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
            if f.suffix.lower() in (".html", ".htm"):
                content = extract_text_from_html(content)
            docs.append({"title": f.name, "content": content, "source": str(f)})
        except Exception as e:
            logger.warning({"event":"rag.read.skip","file":str(f),"err":str(e)})
    return docs

def upsert_chunks(conn, asset_id: str, org_id: str, docs: List[Dict[str, Any]], embeddings: List[List[float]], titles: List[str]):
    with conn:
        with conn.cursor() as cur:
            for i, doc in enumerate(docs):
                chunk_id = "DC-" + uuid.uuid4().hex[:12]
                cur.execute(
                    """
                    INSERT INTO doc_chunks (chunk_id, org_id, asset_id, title, content, source, embedding)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (chunk_id) DO NOTHING
                    """,
                    (chunk_id, org_id, asset_id, titles[i], doc["content"], doc["source"], embeddings[i]),
                )

def ingest_path(path: str, asset_id: str, chunk_size: int = 1200, bulk_mode: bool = False):
    """
    Ingest documents from path into RAG store.
    - chunk_size: Max characters per chunk
    - bulk_mode: If True, chunk each document; if False, one chunk per file
    """
    s = Settings()
    conn = with_pg(s.pg_dsn)
    try:
        docs = load_texts(path)
        if not docs:
            logger.info({"event":"rag.empty","note":"No docs found"})
            return

        all_chunks = []
        all_titles = []

        for doc in docs:
            if bulk_mode:
                # Chunk the document
                chunks = chunk_text(doc["content"], max_chars=chunk_size)
                for i, chunk in enumerate(chunks):
                    all_chunks.append({
                        "title": f"{doc['title']} (chunk {i+1})",
                        "content": chunk,
                        "source": doc["source"]
                    })
                    all_titles.append(f"{doc['title']} (chunk {i+1})")
            else:
                # One chunk per file
                all_chunks.append(doc)
                all_titles.append(doc["title"])

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.error({"event":"rag.no_api_key","note":"OPENAI_API_KEY not set"})
            return

        texts = [c["content"] for c in all_chunks]
        embs = embed_texts(api_key, texts)
        upsert_chunks(conn, asset_id, s.default_org, all_chunks, embs, all_titles)
        logger.info({"event":"rag.ingested","chunks":len(all_chunks),"asset_id":asset_id,"bulk_mode":bulk_mode})
    finally:
        conn.close()
