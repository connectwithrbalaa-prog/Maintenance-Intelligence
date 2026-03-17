import sys
from types import SimpleNamespace

import maintenance_intelligence.api.health as health_mod
from maintenance_intelligence.api.health import compute_kafka_lag

def test_compute_kafka_lag_signature_exists():
    assert callable(compute_kafka_lag)


def test_compute_kafka_lag_sums_partition_lag(monkeypatch):
    class FakeTopicPartition:
        def __init__(self, topic, partition):
            self.topic = topic
            self.partition = partition

        def __hash__(self):
            return hash((self.topic, self.partition))

        def __eq__(self, other):
            return (self.topic, self.partition) == (other.topic, other.partition)

    class FakeConsumer:
        def __init__(self, *args, **kwargs):
            self.group_id = kwargs.get("group_id")

        def partitions_for_topic(self, topic):
            return {0, 1} if topic == "canonical.event.raised" else None

        def end_offsets(self, tps):
            return {
                tps[0]: 10,
                tps[1]: 4,
            }

        def committed(self, tp):
            return {
                ("canonical.event.raised", 0): 7,
                ("canonical.event.raised", 1): 4,
            }[(tp.topic, tp.partition)]

        def close(self):
            return None

    monkeypatch.setattr(health_mod, "KafkaConsumer", FakeConsumer)
    monkeypatch.setitem(sys.modules, "kafka.structs", SimpleNamespace(TopicPartition=FakeTopicPartition))

    result = compute_kafka_lag(
        "kafka:9092",
        ["agent-rca"],
        ["canonical.event.raised"],
        timeout_ms=500,
    )

    assert result["agent-rca"]["total_lag"] == 3
    assert result["agent-rca"]["partitions"] == [
        {"topic": "canonical.event.raised", "partition": 0, "lag": 3},
        {"topic": "canonical.event.raised", "partition": 1, "lag": 0},
    ]
    assert result["_summary"]["total_lag"] == 3