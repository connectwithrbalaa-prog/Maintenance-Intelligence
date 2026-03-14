import datetime as dt
import json

import psycopg2
from kafka import KafkaConsumer
from loguru import logger

from maintenance_intelligence.api.metrics import wo_drafts_total
from maintenance_intelligence.multitenancy import consumer_topics, event_in_scope
from maintenance_intelligence.runner.config import Settings


def with_pg(dsn: str):
    import time

    while True:
        try:
            return psycopg2.connect(dsn)
        except Exception:
            time.sleep(1)


def push_work_order_to_cms(proposal: dict, approved_by: str | None = None, notes: str | None = None):
    return {
        "status": "pending",
        "cms_reference": None,
        "approved_by": approved_by,
        "notes": notes,
        "message": "Stub CMS handoff; replace with your planner/CMMS integration.",
        "proposal_id": proposal.get("proposal_id"),
    }


def wo_bridge(kafka_bootstrap: str, pg_dsn: str):
    settings = Settings()
    conn = with_pg(pg_dsn)
    cons = KafkaConsumer(
        *consumer_topics(
            ["canonical.recommendation.created"], settings, org_id=settings.default_org
        ),
        bootstrap_servers=kafka_bootstrap,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        group_id="agent-wo-bridge",
        auto_offset_reset="earliest",
    )
    for msg in cons:
        if not event_in_scope(msg.value.get("org_id"), settings, org_id=settings.default_org):
            continue
        rec = msg.value.get("recommendation", {})
        wo_id = f"WO-{rec.get('id','')[:8]}"
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO workorders (wo_id, org_id, asset_id, status, title, description, priority, metadata) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb) "
                    "ON CONFLICT (wo_id) DO NOTHING",
                    (
                        wo_id,
                        msg.value.get("org_id") or settings.default_org,
                        rec.get("asset_id"),
                        "DRAFT",
                        rec.get("title"),
                        rec.get("rationale"),
                        "MEDIUM",
                        json.dumps(
                            {
                                "source": "agent-wo-bridge-stub",
                                "created_at": dt.datetime.utcnow().isoformat() + "Z",
                            }
                        ),
                    ),
                )
        logger.info({"event": "wo_bridge.draft_created", "wo_id": wo_id})
        wo_drafts_total.labels(service="wo_bridge").inc()
