from fastapi import APIRouter, Query
from maintenance_intelligence.runner.config import Settings
import socket, psycopg2
from kafka import KafkaAdminClient
import os
from typing import Dict, Any, List, Tuple
from kafka import KafkaConsumer

def compute_kafka_lag(bootstrap: str, groups: List[str], topics: List[str], timeout_ms: int = 3000) -> Dict[str, Any]:
    """
    Compute approximate consumer group lag by comparing end offsets vs committed offsets.
    Returns { group: { total_lag, partitions: [{topic, partition, lag}] }, "_summary": { total_lag } }
    """
    out: Dict[str, Any] = {}
    summary_total = 0
    try:
        # Create a single consumer to fetch end offsets
        # Note: kafka-python AdminClient offset APIs are limited; we use a consumer instance for both queries.
        base_cons = KafkaConsumer(bootstrap_servers=bootstrap, request_timeout_ms=timeout_ms, consumer_timeout_ms=timeout_ms)
        # Resolve partitions for given topics
        partitions = []
        md = base_cons.partitions_for_topic  # callable property
        for t in topics:
            parts = md(t)
            if not parts:
                continue
            partitions.extend([(t, p) for p in parts])

        end_offsets = {}
        if partitions:
            tps = [type("TP", (), {"topic": t, "partition": p}) for (t, p) in partitions]
            # kafka-python expects TopicPartition objects; we build them this way to avoid direct import
            from kafka.structs import TopicPartition
            tps2 = [TopicPartition(tp.topic, tp.partition) for tp in tps]
            end_offsets = base_cons.end_offsets(tps2)  # {TP: offset}

        for g in groups:
            group_cons = KafkaConsumer(group_id=g, bootstrap_servers=bootstrap, enable_auto_commit=False,
                                       request_timeout_ms=timeout_ms, consumer_timeout_ms=timeout_ms)
            grp_total = 0
            parts_detail = []
            try:
                # Find committed offsets for the same topics/partitions
                from kafka.structs import TopicPartition
                tps2 = [TopicPartition(t, p) for (t, p) in partitions]
                committed = {tp: group_cons.committed(tp) or 0 for tp in tps2}
                for tp, end in end_offsets.items():
                    c = committed.get(tp, 0) or 0
                    lag = max(0, int(end) - int(c))
                    grp_total += lag
                    parts_detail.append({"topic": tp.topic, "partition": tp.partition, "lag": lag})
            except Exception:
                # If committed offsets cannot be fetched due to ACLs/permissions, mark unknown
                parts_detail.append({"topic": "unknown", "partition": -1, "lag": None})
            finally:
                try: group_cons.close()
                except Exception: pass

            out[g] = {"total_lag": grp_total, "partitions": parts_detail}
            summary_total += grp_total

        try: base_cons.close()
        except Exception: pass

        out["_summary"] = {"total_lag": summary_total}
        return out
    except Exception as e:
        return {"error": str(e), "_summary": {"total_lag": None}}

router = APIRouter()

@router.get("/healthz")
def healthz(deep: bool = Query(False, description="Enable deep checks (Kafka/PG)")):
    info = {"status": "ok", "host": socket.gethostname()}
    if not deep:
        return info

    settings = Settings()
    # PG check
    try:
        conn = psycopg2.connect(settings.pg_dsn)
        try:
            with conn, conn.cursor() as cur:
                cur.execute("SELECT 1")
            info["pg"] = "ok"
        finally:
            conn.close()
    except Exception as e:
        info["pg"] = f"error: {e}"
        info["status"] = "degraded"

    # Kafka check
    try:
        admin = KafkaAdminClient(bootstrap_servers=settings.kafka_bootstrap, client_id="mi-health")
        topics = admin.list_topics()
        info["kafka"] = "ok" if topics is not None else "unknown"
    except Exception as e:
        info["kafka"] = f"error: {e}"
        info["status"] = "degraded"

    # Kafka lag (optional)
    try:
        groups = os.getenv("MI_HEALTH_GROUPS", "agent-ingestion,agent-rca,agent-wo-bridge,agent-signals").split(",")
        topics = os.getenv("MI_HEALTH_TOPICS", "canonical.asset.upserted,canonical.event.raised,canonical.recommendation.created").split(",")
        max_lag = int(os.getenv("MI_HEALTH_MAX_LAG", "1000"))
        timeout_s = int(os.getenv("MI_HEALTH_TIMEOUT_S", "5"))
        lag = compute_kafka_lag(settings.kafka_bootstrap, groups, topics, timeout_ms=timeout_s*1000)
        info["kafka_lag"] = lag
        tl = lag.get("_summary", {}).get("total_lag")
        if tl is None or (isinstance(tl, int) and tl > max_lag):
            info["status"] = "degraded"
    except Exception as e:
        info["kafka_lag"] = f"error: {e}"
        info["status"] = "degraded"

    return info
