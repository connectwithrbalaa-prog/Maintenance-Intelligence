from maintenance_intelligence.context import assembler


class _Cursor:
    def __init__(self, calls):
        self.calls = calls
        self.rows = []

    def execute(self, query, params=None):
        self.calls.append((query, tuple(params or ())))
        if "SELECT title FROM workorders" in query:
            self.rows = [("Scoped WO",)]
        else:
            self.rows = []

    def fetchall(self):
        return self.rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _Conn:
    def __init__(self, calls):
        self.calls = calls

    def cursor(self, *args, **kwargs):
        return _Cursor(self.calls)

    def close(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_context_uses_org_scope_and_forwards_org_to_retriever(monkeypatch):
    calls = []
    seen = {}
    monkeypatch.setenv("MI_MULTI_TENANT", "true")
    monkeypatch.setenv("MI_DEFAULT_ORG", "ORG-CTX")
    monkeypatch.setattr(assembler, "with_pg", lambda _dsn: _Conn(calls))

    from maintenance_intelligence.rag import retrieval as retrieval_mod

    class FakeRetriever:
        def __init__(self, *_args, **_kwargs):
            pass

        def retrieve(self, query, asset_id, limit=10, token_budget=4000, org_id=None):
            seen["org_id"] = org_id
            return []

    monkeypatch.setattr(retrieval_mod, "HybridRetriever", FakeRetriever)

    ctx = assembler.get_event_context(
        {"asset_id": "ASSET-CTX", "org_id": "ORG-CTX", "kind": "alarm"}
    )

    assert ctx["asset_id"] == "ASSET-CTX"
    assert any("org_id = %s" in query for query, _ in calls if "FROM workorders" in query)
    assert seen["org_id"] == "ORG-CTX"
