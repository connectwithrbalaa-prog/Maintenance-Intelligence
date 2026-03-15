import pytest
from maintenance_intelligence.rag.retrieval import HybridRetriever
from unittest.mock import MagicMock, patch

def test_hybrid_retriever_combine_scores():
    retriever = HybridRetriever("dummy_db_url")

    # Mock results
    vector_results = [
        {'chunk_id': '1', 'title': 'Doc 1', 'content': 'content1', 'vector_score': 0.9},
        {'chunk_id': '2', 'title': 'Doc 2', 'content': 'content2', 'vector_score': 0.8}
    ]
    bm25_results = [
        {'chunk_id': '1', 'title': 'Doc 1', 'content': 'content1', 'bm25_score': 0.7},
        {'chunk_id': '3', 'title': 'Doc 3', 'content': 'content3', 'bm25_score': 0.6}
    ]

    combined = retriever._combine_scores(vector_results, bm25_results)

    assert len(combined) == 3
    assert [chunk['chunk_id'] for chunk in combined] == ['1', '2', '3']

    chunk_1 = next(c for c in combined if c['chunk_id'] == '1')
    expected_score = 1.0
    assert abs(chunk_1['score'] - expected_score) < 0.01
    assert chunk_1['vector_score_norm'] == 1.0
    assert chunk_1['bm25_score_norm'] == 1.0

def test_apply_token_budget():
    retriever = HybridRetriever("dummy_db_url")

    chunks = [
        {'chunk_id': '1', 'content': 'short text'},  # ~2 tokens
        {'chunk_id': '2', 'content': 'this is a longer piece of text that should use more tokens'},  # ~10 tokens
        {'chunk_id': '3', 'content': 'another short one'},  # ~3 tokens
    ]

    # Budget of 10 tokens should include first two chunks (~12 total, but we take until budget)
    result = retriever._apply_token_budget(chunks, token_budget=10)
    assert len(result) == 2  # First two fit
    assert result[0]['chunk_id'] == '1'
    assert result[1]['chunk_id'] == '2'

def test_bm25_score():
    retriever = HybridRetriever("dummy_db_url")

    query_terms = ['test', 'query']
    doc_text = 'this is a test document with query terms'
    all_docs = [('1', 'title1', doc_text), ('2', 'title2', 'other content')]

    score = retriever._bm25_score(query_terms, doc_text, all_docs)
    assert score > 0

    # Test with no matching terms
    score_no_match = retriever._bm25_score(['nonexistent'], doc_text, all_docs)
    assert score_no_match == 0.0

def test_tokenize():
    retriever = HybridRetriever("dummy_db_url")

    text = "Hello, world! This is a test."
    tokens = retriever._tokenize(text)
    assert 'hello' in tokens
    assert 'world' in tokens
    assert 'test' in tokens
    assert '!' not in tokens  # Punctuation removed