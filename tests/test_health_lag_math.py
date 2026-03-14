from maintenance_intelligence.api.health import compute_kafka_lag

def test_compute_kafka_lag_signature_exists():
    assert callable(compute_kafka_lag)