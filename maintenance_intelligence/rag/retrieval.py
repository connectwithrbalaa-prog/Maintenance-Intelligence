import re
import math
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter
import psycopg2
from maintenance_intelligence.context.assembler import with_pg
from maintenance_intelligence.runner.config import Settings

class HybridRetriever:
    """Hybrid retrieval combining BM25 and vector similarity."""

    def __init__(
        self,
        db_url: str,
        vector_weight: Optional[float] = None,
        bm25_weight: Optional[float] = None,
        settings: Optional[Settings] = None,
    ):
        self.db_url = db_url
        self.settings = settings or Settings()
        default_alpha = min(max(self.settings.rag_vector_alpha, 0.0), 1.0)

        if vector_weight is None and bm25_weight is None:
            self.vector_weight = default_alpha
            self.bm25_weight = 1.0 - default_alpha
        else:
            resolved_vector = default_alpha if vector_weight is None else float(vector_weight)
            resolved_bm25 = (1.0 - default_alpha) if bm25_weight is None else float(bm25_weight)
            total = resolved_vector + resolved_bm25
            if total <= 0:
                self.vector_weight = default_alpha
                self.bm25_weight = 1.0 - default_alpha
            else:
                self.vector_weight = resolved_vector / total
                self.bm25_weight = resolved_bm25 / total

    def retrieve(self, query: str, asset_id: Optional[str] = None, limit: int = 10,
                 token_budget: int = 4000) -> List[Dict[str, Any]]:
        """
        Retrieve relevant chunks using hybrid BM25 + vector search.
        Returns top chunks within token budget.
        """
        # Get vector results
        vector_results = self._vector_search(query, asset_id, limit * 2)

        # Get BM25 results
        bm25_results = self._bm25_search(query, asset_id, limit * 2)

        # Combine scores
        combined = self._combine_scores(vector_results, bm25_results)

        # Sort by combined score and apply token budget
        combined.sort(key=lambda x: (-x['score'], str(x.get('chunk_id', ''))))
        return self._apply_token_budget(combined, token_budget)

    def _vector_search(self, query: str, asset_id: Optional[str], limit: int) -> List[Dict[str, Any]]:
        """Vector similarity search using pgvector."""
        try:
            from maintenance_intelligence.genai.gateway import GenAIGateway
            settings = Settings()
            gateway = GenAIGateway(api_key=settings.openai_api_key, model="text-embedding-3-small")
            embedding = gateway._get_embedding(query)  # Access private method for embedding

            conn = with_pg(self.db_url)
            with conn, conn.cursor() as cur:
                if asset_id:
                    cur.execute("""
                        SELECT chunk_id, title, content, embedding <=> %s::vector as distance
                        FROM doc_chunks
                        WHERE asset_id = %s AND embedding IS NOT NULL
                        ORDER BY embedding <=> %s::vector
                        LIMIT %s
                    """, (embedding, asset_id, embedding, limit))
                else:
                    cur.execute("""
                        SELECT chunk_id, title, content, embedding <=> %s::vector as distance
                        FROM doc_chunks
                        WHERE embedding IS NOT NULL
                        ORDER BY embedding <=> %s::vector
                        LIMIT %s
                    """, (embedding, embedding, limit))

                results = cur.fetchall()
                return [{
                    'chunk_id': r[0],
                    'title': r[1],
                    'content': r[2],
                    'vector_score': 1.0 / (1.0 + r[3])  # Convert distance to similarity
                } for r in results]
        except Exception:
            # Fallback to BM25 only if vector search fails
            return []

    def _bm25_search(self, query: str, asset_id: Optional[str], limit: int) -> List[Dict[str, Any]]:
        """BM25 text search."""
        # Tokenize query
        query_terms = self._tokenize(query)

        conn = with_pg(self.db_url)
        with conn, conn.cursor() as cur:
            # Get all documents
            if asset_id:
                cur.execute("SELECT chunk_id, title, content FROM doc_chunks WHERE asset_id = %s", (asset_id,))
            else:
                cur.execute("SELECT chunk_id, title, content FROM doc_chunks")

            docs = cur.fetchall()

            scored = []
            for chunk_id, title, content in docs:
                text = f"{title} {content}"
                bm25_score = self._bm25_score(query_terms, text, docs)
                scored.append({
                    'chunk_id': chunk_id,
                    'title': title,
                    'content': content,
                    'bm25_score': bm25_score
                })

            # Sort by BM25 score
            scored.sort(key=lambda x: x['bm25_score'], reverse=True)
            return scored[:limit]

    def _combine_scores(self, vector_results: List[Dict], bm25_results: List[Dict]) -> List[Dict]:
        """Combine vector and BM25 scores with normalization."""
        vector_dict = {r['chunk_id']: r for r in vector_results}
        bm25_dict = {r['chunk_id']: r for r in bm25_results}
        vector_scores = self._normalize_score_map(vector_dict, 'vector_score')
        bm25_scores = self._normalize_score_map(bm25_dict, 'bm25_score')

        all_chunk_ids = sorted(set(vector_dict.keys()) | set(bm25_dict.keys()))
        combined = []

        for chunk_id in all_chunk_ids:
            combined_score = (
                self.vector_weight * vector_scores.get(chunk_id, 0.0)
                + self.bm25_weight * bm25_scores.get(chunk_id, 0.0)
            )

            data = {
                **bm25_dict.get(chunk_id, {}),
                **vector_dict.get(chunk_id, {}),
                'chunk_id': chunk_id,
                'vector_score_norm': vector_scores.get(chunk_id, 0.0),
                'bm25_score_norm': bm25_scores.get(chunk_id, 0.0),
            }
            data['score'] = combined_score
            combined.append(data)

        return combined

    def _normalize_score_map(self, results: Dict[str, Dict[str, Any]], score_key: str) -> Dict[str, float]:
        raw_scores = {
            chunk_id: float(result.get(score_key, 0.0))
            for chunk_id, result in results.items()
            if result.get(score_key) is not None
        }
        if not raw_scores:
            return {}

        min_score = min(raw_scores.values())
        max_score = max(raw_scores.values())
        if math.isclose(min_score, max_score):
            return {chunk_id: 1.0 for chunk_id in raw_scores}

        scale = max_score - min_score
        return {
            chunk_id: (score - min_score) / scale for chunk_id, score in raw_scores.items()
        }

    def _apply_token_budget(self, chunks: List[Dict], token_budget: int) -> List[Dict]:
        """Select top chunks within token budget using a coarse character-based estimate."""
        selected = []
        total_tokens = 0

        for chunk in chunks:
            content = chunk.get('content', '')
            tokens = max(1, len(content) // 6)
            if total_tokens + tokens <= token_budget:
                selected.append(chunk)
                total_tokens += tokens
            else:
                break

        return selected

    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenization."""
        # Lowercase, remove punctuation, split
        text = re.sub(r'[^\w\s]', '', text.lower())
        return text.split()

    def _bm25_score(self, query_terms: List[str], doc_text: str, all_docs: List[Tuple]) -> float:
        """Calculate BM25 score for a document."""
        doc_terms = self._tokenize(doc_text)
        doc_term_freq = Counter(doc_terms)

        # Document length
        doc_len = len(doc_terms)
        avg_doc_len = sum(len(self._tokenize(f"{title} {content}")) for _, title, content in all_docs) / len(all_docs)

        k1 = 1.5  # BM25 parameters
        b = 0.75

        score = 0.0
        for term in query_terms:
            if term in doc_term_freq:
                tf = doc_term_freq[term]
                df = sum(1 for _, title, content in all_docs if term in self._tokenize(f"{title} {content}"))
                idf = math.log(1 + ((len(all_docs) - df + 0.5) / (df + 0.5)))

                numerator = tf * (k1 + 1)
                denominator = tf + k1 * (1 - b + b * (doc_len / avg_doc_len))
                score += idf * (numerator / denominator)

        return score