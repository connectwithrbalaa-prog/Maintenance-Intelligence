from datetime import datetime, timezone

from maintenance_intelligence.services.pdm_scorer import (
    build_early_warning_report,
    empty_early_warning_summary,
)


def test_build_early_warning_report_ranks_assets_by_persistent_signal_pressure():
    now = datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc)
    report = build_early_warning_report(
        [
            (
                "PUMP-202",
                "high",
                datetime(2026, 3, 18, 10, 0, tzinfo=timezone.utc),
                {"temperature": 92},
            ),
            ("PUMP-202", "high", datetime(2026, 3, 18, 6, 0, tzinfo=timezone.utc), {"rms": 10.4}),
            ("PUMP-202", "medium", datetime(2026, 3, 17, 18, 0, tzinfo=timezone.utc), {"rms": 9.3}),
            ("PUMP-101", "low", datetime(2026, 3, 16, 8, 0, tzinfo=timezone.utc), {"rms": 6.8}),
        ],
        [
            (
                "PUMP-202",
                "vibration",
                "1h",
                datetime(2026, 3, 18, 10, 0, tzinfo=timezone.utc),
                9.8,
                10.7,
                {"high_vibration": True, "z_score_spike": True},
            ),
            (
                "PUMP-202",
                "temperature",
                "6h",
                datetime(2026, 3, 18, 9, 0, tzinfo=timezone.utc),
                88.0,
                91.0,
                {"high_temperature": True},
            ),
            (
                "PUMP-101",
                "vibration",
                "24h",
                datetime(2026, 3, 16, 8, 0, tzinfo=timezone.utc),
                6.4,
                6.9,
                {},
            ),
        ],
        now=now,
    )

    summary = report["summary"]
    assert summary["total_assets"] == 2
    assert summary["status_counts"] == {"critical": 1, "elevated": 0, "watch": 0, "normal": 1}
    assert summary["top_assets"][0]["asset_id"] == "PUMP-202"
    assert summary["top_assets"][0]["status"] == "critical"
    assert summary["top_assets"][0]["score"] == 100.0

    pump_202 = report["asset_metrics"]["PUMP-202"]
    assert pump_202["early_warning_status"] == "critical"
    assert pump_202["early_warning_score"] == 100.0
    assert pump_202["early_warning_reasons"] == [
        "High-severity events have repeated for this asset",
        "Signal rollups still carry anomaly flags",
        "Vibration remains at 10.7 mm/s",
    ]

    pump_101 = report["asset_metrics"]["PUMP-101"]
    assert pump_101["early_warning_status"] == "normal"
    assert pump_101["early_warning_score"] == 18.0
    assert pump_101["early_warning_reasons"] == [
        "Low-volume warning signals are present but not yet persistent"
    ]


def test_build_early_warning_report_keeps_rollup_only_assets_and_emits_watch_status():
    now = datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc)
    report = build_early_warning_report(
        [],
        [
            (
                "FAN-9",
                "temperature",
                "1h",
                datetime(2026, 3, 18, 11, 0, tzinfo=timezone.utc),
                84.0,
                86.0,
                {"high_temperature": True},
            ),
            (
                "FAN-9",
                "temperature",
                "6h",
                datetime(2026, 3, 18, 10, 0, tzinfo=timezone.utc),
                82.0,
                84.0,
                {"high_temperature": True},
            ),
            (
                "FAN-9",
                "temperature",
                "24h",
                datetime(2026, 3, 18, 9, 0, tzinfo=timezone.utc),
                80.0,
                82.0,
                {"high_temperature": True},
            ),
        ],
        now=now,
    )

    assert report["summary"]["status_counts"] == {
        "critical": 0,
        "elevated": 0,
        "watch": 1,
        "normal": 0,
    }
    assert report["asset_metrics"]["FAN-9"]["early_warning_status"] == "watch"
    assert report["asset_metrics"]["FAN-9"]["early_warning_score"] == 26.0
    assert report["asset_metrics"]["FAN-9"]["early_warning_reasons"] == [
        "Signal rollups still carry anomaly flags",
        "Temperature is trending high at 86.0 C",
    ]


def test_empty_early_warning_summary_returns_predictable_shape():
    assert empty_early_warning_summary() == {
        "total_assets": 0,
        "status_counts": {"critical": 0, "elevated": 0, "watch": 0, "normal": 0},
        "top_assets": [],
        "last_evaluated_at": None,
    }
