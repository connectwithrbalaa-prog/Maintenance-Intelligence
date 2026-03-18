import datetime as dt

from maintenance_intelligence.context.assembler import (
    _build_rag_query,
    get_context_cache_snapshot,
    get_event_context,
    prefetch_event_contexts,
    reset_context_cache,
)
from maintenance_intelligence.runner.config import Settings


class FakeCursor:
    def __init__(self, responses):
        self._responses = responses
        self._current = []

    def execute(self, _query, _params=None):
        self._current = next(self._responses)

    def fetchall(self):
        return self._current

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    def __init__(self, responses):
        self._responses = iter(responses)
        self.closed = False

    def cursor(self):
        return FakeCursor(self._responses)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def close(self):
        self.closed = True


def test_context_smoke():
    reset_context_cache()
    evt = {"asset_id": "TEST-ASSET", "kind": "alarm"}
    ctx = get_event_context(evt)
    assert "asset_id" in ctx


def test_build_rag_query_is_explicit_and_stable():
    query = _build_rag_query(
        {
            "kind": "alarm",
            "summary": "pump vibration high",
            "details": {"temperature": 88, "severity": "critical"},
        }
    )

    assert query == "alarm pump vibration high critical 88"


def test_build_rag_query_is_order_invariant_for_details():
    first = _build_rag_query(
        {
            "kind": "alarm",
            "summary": "pump vibration high",
            "details": {
                "severity": "critical",
                "metrics": {"temperature": 88, "pressure": 41},
                "tags": ["pump", "motor"],
            },
        }
    )

    second = _build_rag_query(
        {
            "kind": "alarm",
            "summary": "pump vibration high",
            "details": {
                "tags": ["pump", "motor"],
                "metrics": {"pressure": 41, "temperature": 88},
                "severity": "critical",
            },
        }
    )

    assert first == second == "alarm pump vibration high 41 88 critical pump motor"


def test_get_event_context_uses_retriever_and_preserves_recent_order():
    reset_context_cache()
    fake_conn = FakeConnection(
        [
            [("WO newest",), ("WO older",)],
            [("temperature", "1h", 71.2, 68.0, 74.5, {"high_temp": True})],
            [
                ("SIG-2", "temperature", 91.0, dt.datetime(2026, 3, 15, 12, 30), {"event_id": "EVT-1"}),
                ("SIG-1", "temperature", 89.0, dt.datetime(2026, 3, 15, 12, 15), {}),
            ],
        ]
    )

    class FakeRetriever:
        def __init__(self, dsn):
            self.dsn = dsn

        def retrieve(self, query, asset_id, limit, token_budget, fleet_wide):
            assert query == "alarm pump vibration high 88"
            assert asset_id == "TEST-ASSET"
            assert limit == 5
            assert token_budget == 2000
            assert fleet_wide is True
            return [
                {"chunk_id": "DOC-9", "title": "Manual excerpt", "asset_id": "TEST-ASSET", "source": "manual.pdf", "org_id": None, "site_id": None, "asset_class": None, "source_scope": "local"},
                {"chunk_id": "DOC-2", "title": "Past incident", "asset_id": "PUMP-202", "source": "incident.md", "org_id": None, "site_id": None, "asset_class": None, "source_scope": "fleet"},
            ]

    ctx = get_event_context(
        {"asset_id": "TEST-ASSET", "kind": "alarm", "summary": "pump vibration high", "details": {"temperature": 88}},
        connection_factory=lambda _dsn: fake_conn,
        retriever_cls=FakeRetriever,
        fleet_wide=True,
    )

    assert ctx["last_wo_titles"] == ["WO newest", "WO older"]
    assert ctx["signal_rollups"][0]["signal_type"] == "temperature"
    assert ctx["recent_signals"][0]["signal_id"] == "SIG-2"
    assert ctx["recent_signals"][1]["signal_id"] == "SIG-1"
    assert ctx["doc_chunks"] == [
        {"chunk_id": "DOC-9", "title": "Manual excerpt", "asset_id": "TEST-ASSET", "source": "manual.pdf", "org_id": None, "site_id": None, "asset_class": None, "source_scope": "local"},
        {"chunk_id": "DOC-2", "title": "Past incident", "asset_id": "PUMP-202", "source": "incident.md", "org_id": None, "site_id": None, "asset_class": None, "source_scope": "fleet"},
    ]
    assert ctx["context_scope"] == "local+fleet"
    assert ctx["fleet_context_summary"]["external_ref_count"] == 1
    assert ctx["fleet_context_summary"]["referenced_asset_ids"] == ["PUMP-202"]
    assert fake_conn.closed is True


def test_get_event_context_falls_back_to_doc_chunk_query_when_retriever_fails():
    reset_context_cache()
    fake_conn = FakeConnection(
        [
            [("WO newest",)],
            [],
            [],
            [
                ("DOC-3", "General manual", "routine inspection checklist", "TEST-ASSET", "manual.pdf", dt.datetime(2026, 3, 15, 12, 35)),
                ("DOC-1", "Pump alarm playbook", "pump vibration response steps", "TEST-ASSET", "playbook.md", dt.datetime(2026, 3, 15, 12, 10)),
                ("DOC-2", "Pump maintenance", "bearing wear and pump vibration guide", "TEST-ASSET", "maintenance.md", dt.datetime(2026, 3, 15, 12, 20)),
            ],
        ]
    )

    class FailingRetriever:
        def __init__(self, dsn):
            self.dsn = dsn

        def retrieve(self, query, asset_id, limit, token_budget, fleet_wide):
            raise RuntimeError("retriever unavailable")

    ctx = get_event_context(
        {"asset_id": "TEST-ASSET", "kind": "alarm", "summary": "pump vibration"},
        connection_factory=lambda _dsn: fake_conn,
        retriever_cls=FailingRetriever,
    )

    assert ctx["last_wo_titles"] == ["WO newest"]
    assert ctx["signal_rollups"] == []
    assert ctx["recent_signals"] == []
    assert ctx["doc_chunks"] == [
        {"chunk_id": "DOC-1", "title": "Pump alarm playbook", "asset_id": "TEST-ASSET", "source": "playbook.md", "org_id": None, "site_id": None, "asset_class": None, "source_scope": "local"},
        {"chunk_id": "DOC-2", "title": "Pump maintenance", "asset_id": "TEST-ASSET", "source": "maintenance.md", "org_id": None, "site_id": None, "asset_class": None, "source_scope": "local"},
        {"chunk_id": "DOC-3", "title": "General manual", "asset_id": "TEST-ASSET", "source": "manual.pdf", "org_id": None, "site_id": None, "asset_class": None, "source_scope": "local"},
    ]
    assert ctx["context_scope"] == "local"


def test_get_event_context_reuses_fresh_cached_payload():
    reset_context_cache()

    fake_conn = FakeConnection(
        [
            [("WO newest",)],
            [],
            [],
            [("DOC-1", "Playbook", "pump vibration guide", "TEST-ASSET", "playbook.md", dt.datetime(2026, 3, 15, 12, 10))],
        ]
    )
    settings = Settings(context_cache_enabled=True, context_cache_ttl_s=60, context_cache_max_entries=8)
    event = {"asset_id": "TEST-ASSET", "kind": "alarm", "summary": "pump vibration"}

    first = get_event_context(event, settings=settings, connection_factory=lambda _dsn: fake_conn)
    second = get_event_context(event, settings=settings, connection_factory=lambda _dsn: (_ for _ in ()).throw(AssertionError("should hit cache")))

    assert first["context_cache"]["status"] == "miss"
    assert second["context_cache"]["status"] == "hit"
    assert second["last_wo_titles"] == ["WO newest"]

    snapshot = get_context_cache_snapshot()
    assert snapshot["entries"] == 1
    assert snapshot["hits"] == 1
    assert snapshot["misses"] == 1


def test_prefetch_event_contexts_warms_cache_for_followup_lookup():
    reset_context_cache()

    fake_conn = FakeConnection(
        [
            [("WO newest",)],
            [],
            [],
            [("DOC-1", "Playbook", "pump vibration guide", "TEST-ASSET", "playbook.md", dt.datetime(2026, 3, 15, 12, 10))],
        ]
    )
    settings = Settings(context_cache_enabled=True, context_cache_ttl_s=60, context_cache_max_entries=8)
    event = {"asset_id": "TEST-ASSET", "kind": "alarm", "summary": "pump vibration"}

    prefetched = prefetch_event_contexts([event], settings=settings, connection_factory=lambda _dsn: fake_conn)
    cached = get_event_context(event, settings=settings, connection_factory=lambda _dsn: (_ for _ in ()).throw(AssertionError("should hit cache")))

    assert prefetched[0]["context_cache"]["status"] == "miss"
    assert cached["context_cache"]["status"] == "hit"

    snapshot = get_context_cache_snapshot()
    assert snapshot["prefetches"] == 1
    assert snapshot["entries"] == 1
