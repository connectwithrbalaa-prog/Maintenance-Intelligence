"""Tests for ISO 14224–aligned RAG retrieval, prompts, and API."""

from fastapi.testclient import TestClient

from maintenance_intelligence.ai.prompts.rca_templates import (
    SYSTEM_PROMPT,
    build_rca_prompt,
    build_pm_optimization_prompt,
)
from maintenance_intelligence.ai.rag.structured_retriever import (
    HierarchyContext,
    FailureHistoryEntry,
    ISOTaxonomyContext,
    RCAContext,
)
from maintenance_intelligence.api.main import app

client = TestClient(app)
HEADERS = {"X-User-Id": "test.engineer", "X-User-Role": "admin", "X-Org-Id": "test-org"}


# ── Structured retriever dataclass tests ──


class TestHierarchyContext:
    def test_to_prompt_text(self):
        ctx = HierarchyContext(
            equipment_unit_id="EQ-001",
            tag="CT-301A",
            iso_equipment_class="CENTRIFUGAL_COMPRESSOR",
            criticality="CRITICAL",
            service_medium="GAS",
            oem_name="Solar Turbines",
            system_name="Gas Compression",
            system_type="GAS_COMPRESSION",
            system_group="PROCESS",
            facility_name="Gulf Platform Alpha",
            facility_type="OFFSHORE_PLATFORM",
            site_name="Gulf Field",
            safety_critical=True,
        )
        text = ctx.to_prompt_text()
        assert "CT-301A" in text
        assert "CENTRIFUGAL_COMPRESSOR" in text
        assert "CRITICAL" in text
        assert "Gas Compression" in text
        assert "Safety critical: Yes" in text


class TestISOTaxonomyContext:
    def test_to_prompt_text(self):
        ctx = ISOTaxonomyContext(
            failure_mode={"code": "VIB", "name": "Vibration", "description": "Abnormal vibration levels"},
            failure_mechanism={"code": "WEA", "name": "Wear", "description": "Material loss from mechanical contact"},
        )
        text = ctx.to_prompt_text()
        assert "VIB" in text
        assert "Vibration" in text
        assert "WEA" in text
        assert "Wear" in text

    def test_empty(self):
        ctx = ISOTaxonomyContext()
        assert "No ISO taxonomy context" in ctx.to_prompt_text()


class TestRCAContext:
    def test_to_prompt_text_full(self):
        ctx = RCAContext(
            hierarchy=HierarchyContext(
                equipment_unit_id="EQ-001", tag="CT-301A",
                iso_equipment_class="CENTRIFUGAL_COMPRESSOR",
            ),
            failure_history=[
                FailureHistoryEntry(event_id="F-1", failure_mode_code="VIB", summary="High vibration", downtime_hours=6),
            ],
            iso_taxonomy=ISOTaxonomyContext(
                failure_mode={"code": "VIB", "name": "Vibration", "description": "Abnormal vibration"},
            ),
            reliability_summary={"mtbf_hours": 2000, "mttr_hours": 8, "availability": 0.996},
        )
        text = ctx.to_prompt_text()
        assert "Equipment context" in text
        assert "CT-301A" in text
        assert "Past failures" in text
        assert "VIB" in text
        assert "Reliability metrics" in text
        assert "2000" in text

    def test_empty(self):
        ctx = RCAContext()
        assert "No structured context" in ctx.to_prompt_text()


# ── Prompt template tests ──


class TestRCAPromptTemplates:
    def test_system_prompt_has_iso_codes(self):
        assert "ISO 14224" in SYSTEM_PROMPT
        assert "failure_mode_code" in SYSTEM_PROMPT
        assert "failure_mechanism_code" in SYSTEM_PROMPT
        assert "repair_plan" in SYSTEM_PROMPT

    def test_build_rca_prompt_minimal(self):
        prompt = build_rca_prompt("High vibration on compressor CT-301A")
        assert "High vibration" in prompt
        assert "ISO 14224" in prompt

    def test_build_rca_prompt_with_context(self):
        ctx = RCAContext(
            hierarchy=HierarchyContext(
                equipment_unit_id="EQ-001", tag="CT-301A",
                iso_equipment_class="CENTRIFUGAL_COMPRESSOR",
            ),
            iso_taxonomy=ISOTaxonomyContext(
                failure_mode={"code": "VIB", "name": "Vibration", "description": "Abnormal vibration"},
            ),
        )
        prompt = build_rca_prompt(
            "High vibration on CT-301A drive-end bearing",
            context=ctx,
            asset_id="CT-301A",
            severity="high",
        )
        assert "CT-301A" in prompt
        assert "CENTRIFUGAL_COMPRESSOR" in prompt
        assert "VIB" in prompt
        assert "Severity: high" in prompt

    def test_build_pm_optimization_prompt(self):
        prompt = build_pm_optimization_prompt(
            "Compressor CT-301A, Gas Compression system",
            "3 failures in 12 months: 2x VIB, 1x ELP",
            "MTBF: 2000h, MTTR: 8h, Availability: 99.6%",
        )
        assert "ISO 14224" in prompt
        assert "MTBF" in prompt
        assert "CT-301A" in prompt


# ── API endpoint tests ──


class TestRAGContextAPI:
    def test_full_context(self):
        resp = client.get("/api/v1/rag/context/EQ-TEST-001", headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert "equipment_unit_id" in data
        assert "failure_history" in data
        assert "prompt_text" in data

    def test_hierarchy_not_found(self):
        resp = client.get("/api/v1/rag/hierarchy/EQ-NONEXISTENT", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["found"] is False

    def test_failure_history(self):
        resp = client.get("/api/v1/rag/failure-history/EQ-TEST-001", headers=HEADERS)
        assert resp.status_code == 200
        assert "entries" in resp.json()

    def test_taxonomy_lookup(self):
        resp = client.get("/api/v1/rag/taxonomy-lookup?failure_mode_code=VIB", headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["failure_mode"]["code"] == "VIB"
        assert "Vibration" in data["failure_mode"]["name"]

    def test_taxonomy_lookup_multiple(self):
        resp = client.get(
            "/api/v1/rag/taxonomy-lookup?failure_mode_code=VIB&failure_mechanism_code=WEA",
            headers=HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["failure_mode"]["code"] == "VIB"
        assert data["failure_mechanism"]["code"] == "WEA"

    def test_similar_failures(self):
        resp = client.get(
            "/api/v1/rag/similar-failures?iso_equipment_class=CENTRIFUGAL_PUMP",
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert "entries" in resp.json()

    def test_requires_auth(self):
        resp = client.get("/api/v1/rag/context/EQ-001")
        assert resp.status_code == 403
