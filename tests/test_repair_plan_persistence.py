from datetime import datetime, timezone

from maintenance_intelligence.services import repair_plan_service as service_mod


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.rows = []
        self.rowcount = 0

    def execute(self, query, params):
        self.connection.executed.append((query, params))
        normalized = " ".join(query.split())
        self.rowcount = 0
        if normalized.startswith("INSERT INTO repair_plan"):
            self.rows = [
                (
                    params[0],
                    params[1],
                    params[2],
                    params[3],
                    params[4],
                    params[5],
                    params[6],
                    params[7],
                    params[8],
                    datetime(2026, 3, 17, 9, 0, tzinfo=timezone.utc),
                    datetime(2026, 3, 17, 9, 0, tzinfo=timezone.utc),
                )
            ]
            return
        if normalized.startswith("DELETE FROM repair_plan"):
            self.rows = []
            self.rowcount = 1 if self.connection.delete_ok else 0
            return
        if "FROM repair_plan WHERE plan_id = %s" in normalized:
            if self.connection.plan_row is None:
                self.rows = []
            else:
                self.rows = [self.connection.plan_row]
            return
        if "FROM repair_plan ORDER BY created_at DESC" in normalized:
            self.rows = list(self.connection.plan_rows)
            return
        if normalized.startswith("INSERT INTO repair_part"):
            self.rows = [
                (
                    params[1],
                    params[0],
                    params[2],
                    params[3],
                    params[4],
                    params[5],
                    {"sku": "BRG-9"},
                    datetime(2026, 3, 17, 9, 5, tzinfo=timezone.utc),
                )
            ]
            return
        if "FROM repair_part WHERE plan_id = %s" in normalized:
            self.rows = list(self.connection.part_rows)
            return
        raise AssertionError(f"Unexpected SQL: {query}")

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    def __init__(self):
        self.executed = []
        self.closed = False
        self.delete_ok = True
        self.plan_row = (
            "RP-123",
            "RUN-123",
            "REC-123",
            "demo-org",
            "PUMP-101",
            "Replace bearing",
            "Vibration trend is rising",
            0.91,
            "pending",
            datetime(2026, 3, 17, 9, 0, tzinfo=timezone.utc),
            datetime(2026, 3, 17, 9, 0, tzinfo=timezone.utc),
        )
        self.plan_rows = [self.plan_row]
        self.part_rows = [
            (
                "PART-123",
                "RP-123",
                "Bearing kit",
                "OEM bearing replacement",
                1,
                "ea",
                {"sku": "BRG-9"},
                datetime(2026, 3, 17, 9, 5, tzinfo=timezone.utc),
            )
        ]

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_repair_plan_service_crud(monkeypatch):
    fake_connection = FakeConnection()
    monkeypatch.setattr(service_mod, "connection_factory", lambda _dsn: fake_connection)

    created = service_mod.create_repair_plan(
        "postgresql://unused",
        run_id="RUN-123",
        recommendation_id="REC-123",
        org_id="demo-org",
        asset_id="PUMP-101",
        summary="Replace bearing",
        rationale="Vibration trend is rising",
        confidence=0.91,
    )
    assert created["plan_id"].startswith("RP-")
    assert created["summary"] == "Replace bearing"

    fetched = service_mod.get_repair_plan("postgresql://unused", "RP-123")
    assert fetched is not None
    assert fetched["recommendation_id"] == "REC-123"

    listed = service_mod.list_repair_plans("postgresql://unused", limit=10)
    assert listed[0]["asset_id"] == "PUMP-101"

    created_part = service_mod.add_part_to_plan(
        "postgresql://unused",
        "RP-123",
        name="Bearing kit",
        description="OEM bearing replacement",
        quantity=1,
        unit="ea",
        metadata={"sku": "BRG-9"},
    )
    assert created_part["plan_id"] == "RP-123"
    assert created_part["metadata"] == {"sku": "BRG-9"}

    parts = service_mod.list_parts_for_plan("postgresql://unused", "RP-123")
    assert parts[0]["name"] == "Bearing kit"

    deleted = service_mod.delete_repair_plan("postgresql://unused", "RP-123")
    assert deleted is True
    assert fake_connection.closed is True
