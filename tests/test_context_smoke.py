import datetime as dt

from maintenance_intelligence.context.assembler import (
    _build_rag_query,
    _rank_fallback_doc_chunks,
    get_event_context,
)


def test_context_smoke():
    evt = {"asset_id": "TEST-ASSET", "kind": "alarm"}
    ctx = get_event_context(evt)
    assert "asset_id" in ctx


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


def test_rank_fallback_doc_chunks_prefers_relevant_matches_then_recency():
    ranked = _rank_fallback_doc_chunks(
        [
            ("DOC-3", "General manual", "routine inspection checklist", dt.datetime(2026, 3, 15, 12, 35)),
            ("DOC-1", "Pump alarm playbook", "pump vibration response steps", dt.datetime(2026, 3, 15, 12, 10)),
            ("DOC-2", "Pump maintenance", "bearing wear and pump vibration guide", dt.datetime(2026, 3, 15, 12, 20)),
        ],
        "alarm pump vibration",
    )

    assert ranked == [
        {"chunk_id": "DOC-1", "title": "Pump alarm playbook"},
        {"chunk_id": "DOC-2", "title": "Pump maintenance"},
        {"chunk_id": "DOC-3", "title": "General manual"},
    ]
