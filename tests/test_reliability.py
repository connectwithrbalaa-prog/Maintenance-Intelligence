"""Tests for reliability calculators and API endpoints."""

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from maintenance_intelligence.api.main import app
from maintenance_intelligence.core.reliability.calculator import (
    FailureInterval,
    ReliabilityMetrics,
    calculate_availability,
    calculate_failure_rate,
    calculate_mtbf,
    calculate_mttr,
    calculate_reliability,
)

client = TestClient(app)
HEADERS = {"X-User-Id": "test.engineer", "X-User-Role": "admin", "X-Org-Id": "test-org"}


# ── Unit calculator tests ──


class TestMTBF:
    def test_normal(self):
        assert calculate_mtbf(1000, 5) == 200.0

    def test_zero_failures(self):
        assert calculate_mtbf(1000, 0) is None

    def test_zero_hours(self):
        assert calculate_mtbf(0, 5) is None


class TestMTTR:
    def test_normal(self):
        assert calculate_mttr(50, 5) == 10.0

    def test_zero_failures(self):
        assert calculate_mttr(50, 0) is None


class TestAvailability:
    def test_normal(self):
        result = calculate_availability(200, 10)
        assert result is not None
        assert abs(result - 0.9524) < 0.001

    def test_perfect(self):
        result = calculate_availability(1000, 0)
        assert result == 1.0  # MTTR=0 → perfect availability

    def test_none_inputs(self):
        assert calculate_availability(None, 10) is None
        assert calculate_availability(200, None) is None


class TestFailureRate:
    def test_normal(self):
        result = calculate_failure_rate(1000, 5)
        assert result is not None
        assert abs(result - 0.005) < 0.0001

    def test_zero(self):
        assert calculate_failure_rate(0, 5) is None


class TestCalculateReliability:
    def test_empty_failures(self):
        result = calculate_reliability([])
        assert result.failure_count == 0
        assert result.mtbf_hours is None

    def test_single_failure_with_downtime(self):
        now = datetime.utcnow()
        failures = [
            FailureInterval(
                event_id="F-001",
                failure_start=now - timedelta(hours=100),
                restoration=now - timedelta(hours=94),
                downtime_hours=6,
            ),
        ]
        result = calculate_reliability(
            failures,
            observation_start=now - timedelta(hours=200),
            observation_end=now,
        )
        assert result.failure_count == 1
        assert result.total_downtime_hours == 6.0
        assert result.total_operating_hours == 194.0
        assert result.mtbf_hours == 194.0
        assert result.mttr_hours == 6.0
        assert result.availability is not None
        assert result.availability > 0.95

    def test_multiple_failures(self):
        now = datetime.utcnow()
        failures = [
            FailureInterval("F-1", now - timedelta(hours=90), now - timedelta(hours=86)),
            FailureInterval("F-2", now - timedelta(hours=50), now - timedelta(hours=46)),
            FailureInterval("F-3", now - timedelta(hours=10), now - timedelta(hours=8)),
        ]
        result = calculate_reliability(
            failures,
            observation_start=now - timedelta(hours=100),
            observation_end=now,
        )
        assert result.failure_count == 3
        assert result.failures_with_downtime == 3
        assert result.total_downtime_hours == 10.0
        assert result.total_operating_hours == 90.0
        assert result.mtbf_hours == 30.0
        assert result.failure_rate is not None

    def test_failure_without_restoration(self):
        now = datetime.utcnow()
        failures = [
            FailureInterval("F-1", now - timedelta(hours=50)),
        ]
        result = calculate_reliability(
            failures,
            observation_start=now - timedelta(hours=100),
            observation_end=now,
        )
        assert result.failure_count == 1
        assert result.failures_without_downtime == 1
        assert result.total_downtime_hours == 0.0
        assert result.mttr_hours is None

    def test_to_dict(self):
        result = calculate_reliability([])
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "failure_count" in d
        assert "mtbf_hours" in d


# ── API endpoint tests ──


class TestReliabilityAPI:
    def test_equipment_reliability(self):
        resp = client.get("/api/v1/reliability/equipment/EQ-TEST-001", headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert "failure_count" in data
        assert "mtbf_hours" in data
        assert "availability" in data

    def test_asset_reliability(self):
        resp = client.get("/api/v1/reliability/asset/CT-301A", headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert "failure_count" in data

    def test_fleet_reliability(self):
        resp = client.get("/api/v1/reliability/fleet", headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert "window_days" in data
        assert "equipment_count" in data
        assert "equipment" in data

    def test_fleet_with_filters(self):
        resp = client.get(
            "/api/v1/reliability/fleet?iso_equipment_class=CENTRIFUGAL_PUMP&window_days=90",
            headers=HEADERS,
        )
        assert resp.status_code == 200

    def test_requires_auth(self):
        resp = client.get("/api/v1/reliability/equipment/EQ-001")
        assert resp.status_code == 403
