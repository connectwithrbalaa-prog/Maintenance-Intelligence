from maintenance_intelligence.rag.retrieval import HybridRetriever
from maintenance_intelligence.runner.config import Settings


def test_normalize_score_map_scales_candidate_scores_to_unit_interval():
    retriever = HybridRetriever("dummy_db_url")

    normalized = retriever._normalize_score_map(
        {
            "chunk-b": {"bm25_score": 2.0},
            "chunk-a": {"bm25_score": 5.0},
            "chunk-c": {"bm25_score": 3.5},
        },
        "bm25_score",
    )

    assert normalized == {
        "chunk-b": 0.0,
        "chunk-a": 1.0,
        "chunk-c": 0.5,
    }


def test_normalize_score_map_returns_full_weight_for_flat_scores():
    retriever = HybridRetriever("dummy_db_url")

    normalized = retriever._normalize_score_map(
        {
            "chunk-a": {"vector_score": 0.4},
            "chunk-b": {"vector_score": 0.4},
        },
        "vector_score",
    )

    assert normalized == {"chunk-a": 1.0, "chunk-b": 1.0}


def test_hybrid_retriever_uses_configurable_vector_alpha(monkeypatch):
    monkeypatch.setenv("MI_RAG_VECTOR_ALPHA", "0.6")

    retriever = HybridRetriever("dummy_db_url", settings=Settings())

    assert retriever.vector_weight == 0.6
    assert retriever.bm25_weight == 0.4


def test_combine_scores_respects_normalized_weighting():
    retriever = HybridRetriever("dummy_db_url", vector_weight=0.6, bm25_weight=0.4)

    combined = retriever._combine_scores(
        [
            {"chunk_id": "chunk-a", "title": "Doc A", "content": "a", "vector_score": 0.9},
            {"chunk_id": "chunk-b", "title": "Doc B", "content": "b", "vector_score": 0.6},
        ],
        [
            {"chunk_id": "chunk-a", "title": "Doc A", "content": "a", "bm25_score": 2.0},
            {"chunk_id": "chunk-b", "title": "Doc B", "content": "b", "bm25_score": 5.0},
        ],
    )

    scores = {chunk["chunk_id"]: chunk["score"] for chunk in combined}

    assert scores["chunk-a"] == 0.6
    assert scores["chunk-b"] == 0.4


def test_retrieve_ranking_is_stable_across_input_permutations():
    class StubRetriever(HybridRetriever):
        def __init__(self, vector_results, bm25_results):
            super().__init__("dummy_db_url", vector_weight=0.6, bm25_weight=0.4)
            self._vector_results = vector_results
            self._bm25_results = bm25_results

        def _vector_search(self, query, asset_id, limit, org_id=None):
            return list(self._vector_results)

        def _bm25_search(self, query, asset_id, limit, org_id=None):
            return list(self._bm25_results)

    first = StubRetriever(
        [
            {"chunk_id": "chunk-2", "title": "Doc 2", "content": "bbb", "vector_score": 0.8},
            {"chunk_id": "chunk-1", "title": "Doc 1", "content": "aaa", "vector_score": 0.8},
        ],
        [
            {"chunk_id": "chunk-1", "title": "Doc 1", "content": "aaa", "bm25_score": 1.5},
            {"chunk_id": "chunk-2", "title": "Doc 2", "content": "bbb", "bm25_score": 1.5},
        ],
    )
    second = StubRetriever(
        [
            {"chunk_id": "chunk-1", "title": "Doc 1", "content": "aaa", "vector_score": 0.8},
            {"chunk_id": "chunk-2", "title": "Doc 2", "content": "bbb", "vector_score": 0.8},
        ],
        [
            {"chunk_id": "chunk-2", "title": "Doc 2", "content": "bbb", "bm25_score": 1.5},
            {"chunk_id": "chunk-1", "title": "Doc 1", "content": "aaa", "bm25_score": 1.5},
        ],
    )

    first_ranked = first.retrieve("pump", limit=2, token_budget=50)
    second_ranked = second.retrieve("pump", limit=2, token_budget=50)

    assert [chunk["chunk_id"] for chunk in first_ranked] == ["chunk-1", "chunk-2"]
    assert [chunk["chunk_id"] for chunk in second_ranked] == ["chunk-1", "chunk-2"]