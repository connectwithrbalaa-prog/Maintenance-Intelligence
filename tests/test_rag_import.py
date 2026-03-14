def test_rag_imports():
    from maintenance_intelligence.rag import ingest
    assert hasattr(ingest, "ingest_path")
