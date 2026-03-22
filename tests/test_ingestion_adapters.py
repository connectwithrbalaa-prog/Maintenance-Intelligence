"""Tests for ingestion adapters — SAP PM, Maximo, SCADA."""

from datetime import datetime

from maintenance_intelligence.ingestion.base import (
    CanonicalEquipment,
    CanonicalFailureEvent,
    CanonicalSignal,
    CanonicalWorkOrder,
    IngestionResult,
)
from maintenance_intelligence.ingestion.sap_pm.adapter import SAPPMAdapter
from maintenance_intelligence.ingestion.maximo.adapter import MaximoIngestionAdapter
from maintenance_intelligence.ingestion.scada.adapter import SCADAAdapter, TagMapping


# ── SAP PM Adapter ──


class TestSAPPMAdapter:
    def test_normalize_equipment(self):
        adapter = SAPPMAdapter(tenant_id="test-tenant")
        result = adapter.normalize_equipment({
            "EQUNR": "000012345",
            "TPLNR": "PLANT-01-P-101",
            "EQART": "PUMP",
            "HERST": "Sulzer",
            "TYPBZ": "MSD-RO",
        })
        assert isinstance(result, CanonicalEquipment)
        assert result.equipment_unit_id == "SAP-000012345"
        assert result.tag == "PLANT-01-P-101"
        assert result.iso_equipment_class == "CENTRIFUGAL_PUMP"
        assert result.oem_name == "Sulzer"
        assert result.tenant_id == "test-tenant"

    def test_normalize_notification(self):
        adapter = SAPPMAdapter(tenant_id="test-tenant")
        result = adapter.normalize_notification({
            "QMNUM": "000100001",
            "EQUNR": "000012345",
            "TPLNR": "PLANT-01-P-101",
            "QMTXT": "High vibration on P-101 drive end",
            "PRIOK": "2",
            "FECOD": "WEAR",
            "URCOD": "OPER",
            "OTEIL": "BEAR",
            "QMART": "M3",
            "AUSVN": "20260320100000",
            "AUSBS": "20260320160000",
        })
        assert isinstance(result, CanonicalFailureEvent)
        assert result.event_id == "SAP-NOTIF-000100001"
        assert result.source_system == "SAP"
        assert result.equipment_unit_id == "SAP-000012345"
        assert result.severity == "HIGH"
        assert result.kind == "alarm"
        assert result.downtime_hours == 6.0
        assert result.detection_method_code == "MON"
        assert result.details["sap_damage_code"] == "WEAR"

    def test_normalize_order(self):
        adapter = SAPPMAdapter(tenant_id="test-tenant")
        result = adapter.normalize_order({
            "AUFNR": "000400001",
            "EQUNR": "000012345",
            "AUART": "PM01",
            "PRIOK": "1",
            "KTEXT": "Replace drive-end bearing on P-101",
            "STAT": "REL",
            "GSTRP": "20260321",
        })
        assert isinstance(result, CanonicalWorkOrder)
        assert result.wo_id == "SAP-ORDER-000400001"
        assert result.maintenance_type == "CORRECTIVE"
        assert result.priority == "CRITICAL"
        assert result.status == "IN_PROGRESS"
        assert result.planned_start_ts == datetime(2026, 3, 21)

    def test_fetch_equipment_batch(self):
        adapter = SAPPMAdapter()
        records = [
            {"EQUNR": "001", "TPLNR": "P-101", "EQART": "GAS_TURB"},
            {"EQUNR": "002", "TPLNR": "K-201", "EQART": "CENT_COMP"},
        ]
        results = adapter.fetch_equipment(records=records)
        assert len(results) == 2
        assert results[0].iso_equipment_class == "GAS_TURBINE"
        assert results[1].iso_equipment_class == "CENTRIFUGAL_COMPRESSOR"

    def test_connection_not_configured(self):
        adapter = SAPPMAdapter()
        status = adapter.test_connection()
        assert status["status"] == "not_configured"


# ── Maximo Adapter ──


class TestMaximoIngestionAdapter:
    def test_normalize_asset(self):
        adapter = MaximoIngestionAdapter(tenant_id="mx-tenant")
        result = adapter.normalize_asset({
            "assetnum": "PUMP-201",
            "assettype": "PUMP",
            "location": "UNIT-3",
            "vendor": "Flowserve",
            "modelnum": "HPX-2000",
        })
        assert isinstance(result, CanonicalEquipment)
        assert result.equipment_unit_id == "MX-PUMP-201"
        assert result.iso_equipment_class == "CENTRIFUGAL_PUMP"
        assert result.oem_name == "Flowserve"

    def test_normalize_work_order(self):
        adapter = MaximoIngestionAdapter(tenant_id="mx-tenant")
        result = adapter.normalize_work_order({
            "wonum": "WO-5001",
            "assetnum": "PUMP-201",
            "worktype": "CM",
            "wopriority": 2,
            "description": "Replace mechanical seal",
            "status": "INPRG",
            "schedstart": "2026-03-21T08:00:00",
        })
        assert isinstance(result, CanonicalWorkOrder)
        assert result.wo_id == "MX-WO-WO-5001"
        assert result.maintenance_type == "CORRECTIVE"
        assert result.status == "IN_PROGRESS"
        assert result.priority == "HIGH"

    def test_normalize_failure_report(self):
        adapter = MaximoIngestionAdapter(tenant_id="mx-tenant")
        result = adapter.normalize_failure_report({
            "wonum": "WO-5001",
            "assetnum": "PUMP-201",
            "failurecode": "VIBRATION",
            "cause": "WEAR",
            "remedy": "REPLACE",
            "description": "High vibration due to bearing wear",
            "wopriority": 1,
        })
        assert isinstance(result, CanonicalFailureEvent)
        assert result.event_id == "MX-FAIL-WO-5001-VIBRATION"
        assert result.source_system == "MAXIMO"
        assert result.kind == "alarm"
        assert result.details["maximo_problem"] == "VIBRATION"

    def test_connection_not_configured(self):
        adapter = MaximoIngestionAdapter()
        status = adapter.test_connection()
        assert status["status"] == "not_configured"


# ── SCADA Adapter ──


class TestSCADAAdapter:
    def _make_adapter(self):
        mapping = TagMapping()
        mapping.add("CT301A_VIB_DE", "EQ-CT301A", "vibration", component_id="COMP-BEAR-DE")
        mapping.add("CT301A_TEMP_DE", "EQ-CT301A", "temperature")
        mapping.add("PS105B_SEAL_P", "EQ-PS105B", "pressure", unit="bar")
        return SCADAAdapter(tag_mapping=mapping, tenant_id="scada-tenant")

    def test_normalize_reading(self):
        adapter = self._make_adapter()
        result = adapter.normalize_reading({
            "tag": "CT301A_VIB_DE",
            "value": 9.4,
            "timestamp": "2026-03-21T10:30:00Z",
            "quality": "GOOD",
        })
        assert isinstance(result, CanonicalSignal)
        assert result.equipment_unit_id == "EQ-CT301A"
        assert result.component_id == "COMP-BEAR-DE"
        assert result.signal_type == "vibration"
        assert result.value == 9.4
        assert result.unit == "mm/s"
        assert result.metadata["scada_tag"] == "CT301A_VIB_DE"

    def test_unmapped_tag_returns_none(self):
        adapter = self._make_adapter()
        result = adapter.normalize_reading({"tag": "UNKNOWN_TAG", "value": 42})
        assert result is None

    def test_fetch_signals_batch(self):
        adapter = self._make_adapter()
        readings = [
            {"tag": "CT301A_VIB_DE", "value": 9.4, "timestamp": "2026-03-21T10:30:00Z"},
            {"tag": "CT301A_TEMP_DE", "value": 85.2, "timestamp": "2026-03-21T10:30:00Z"},
            {"tag": "UNKNOWN", "value": 0},
            {"tag": "PS105B_SEAL_P", "value": 2.96, "timestamp": "2026-03-21T10:30:00Z"},
        ]
        results = adapter.fetch_signals(readings=readings)
        assert len(results) == 3
        assert results[0].signal_type == "vibration"
        assert results[1].signal_type == "temperature"
        assert results[2].signal_type == "pressure"
        assert results[2].unit == "bar"

    def test_tag_mapping_count(self):
        adapter = self._make_adapter()
        status = adapter.test_connection()
        assert status["mapped_tags"] == 3

    def test_empty_readings(self):
        adapter = self._make_adapter()
        assert adapter.fetch_signals(readings=[]) == []
        assert adapter.fetch_signals() == []


# ── Base types ──


class TestIngestionResult:
    def test_success(self):
        result = IngestionResult(source_system="SAP", adapter_name="sap_pm", equipment_count=10)
        assert result.success is True

    def test_failure(self):
        result = IngestionResult(source_system="SAP", adapter_name="sap_pm", error_count=2, errors=["err1", "err2"])
        assert result.success is False
