import json
import uuid
from datetime import datetime
from typing import Any, Optional

from maintenance_intelligence.context.assembler import with_pg

connection_factory = with_pg


def _isoformat(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _plan_row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "plan_id": row[0],
        "run_id": row[1],
        "recommendation_id": row[2],
        "org_id": row[3],
        "asset_id": row[4],
        "summary": row[5],
        "rationale": row[6],
        "confidence": row[7],
        "status": row[8],
        "created_at": _isoformat(row[9]),
        "updated_at": _isoformat(row[10]),
    }


def _part_row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "part_id": row[0],
        "plan_id": row[1],
        "name": row[2],
        "description": row[3],
        "quantity": row[4],
        "unit": row[5],
        "metadata": row[6] or {},
        "created_at": _isoformat(row[7]),
    }


def create_repair_plan(
    dsn: str,
    *,
    run_id: Optional[str] = None,
    recommendation_id: Optional[str] = None,
    org_id: Optional[str] = None,
    asset_id: Optional[str] = None,
    summary: Optional[str] = None,
    rationale: Optional[str] = None,
    confidence: Optional[float] = None,
    status: str = "pending",
) -> dict[str, Any]:
    conn = connection_factory(dsn)
    try:
        plan_id = "RP-" + uuid.uuid4().hex[:12]
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO repair_plan(
                    plan_id, run_id, recommendation_id, org_id, asset_id,
                    summary, rationale, confidence, status
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING plan_id, run_id, recommendation_id, org_id, asset_id,
                          summary, rationale, confidence, status, created_at, updated_at
                """,
                (
                    plan_id,
                    run_id,
                    recommendation_id,
                    org_id,
                    asset_id,
                    summary,
                    rationale,
                    confidence,
                    status,
                ),
            )
            row = cur.fetchone()
        return _plan_row_to_dict(row)
    finally:
        conn.close()


def get_repair_plan(dsn: str, plan_id: str) -> Optional[dict[str, Any]]:
    conn = connection_factory(dsn)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT plan_id, run_id, recommendation_id, org_id, asset_id,
                       summary, rationale, confidence, status, created_at, updated_at
                FROM repair_plan
                WHERE plan_id = %s
                """,
                (plan_id,),
            )
            row = cur.fetchone()
        return _plan_row_to_dict(row) if row else None
    finally:
        conn.close()


def list_repair_plans(dsn: str, *, limit: int = 100) -> list[dict[str, Any]]:
    conn = connection_factory(dsn)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT plan_id, run_id, recommendation_id, org_id, asset_id,
                       summary, rationale, confidence, status, created_at, updated_at
                FROM repair_plan
                ORDER BY created_at DESC, plan_id DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall() or []
        return [_plan_row_to_dict(row) for row in rows]
    finally:
        conn.close()


def delete_repair_plan(dsn: str, plan_id: str) -> bool:
    conn = connection_factory(dsn)
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM repair_plan WHERE plan_id = %s", (plan_id,))
            deleted = cur.rowcount > 0
        return deleted
    finally:
        conn.close()


def add_part_to_plan(
    dsn: str,
    plan_id: str,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    quantity: Optional[int] = None,
    unit: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    conn = connection_factory(dsn)
    try:
        part_id = "PART-" + uuid.uuid4().hex[:12]
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO repair_part(plan_id, part_id, name, description, quantity, unit, metadata)
                VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
                RETURNING part_id, plan_id, name, description, quantity, unit, metadata, created_at
                """,
                (
                    plan_id,
                    part_id,
                    name,
                    description,
                    quantity,
                    unit,
                    json.dumps(metadata) if metadata is not None else None,
                ),
            )
            row = cur.fetchone()
        return _part_row_to_dict(row)
    finally:
        conn.close()


def list_parts_for_plan(dsn: str, plan_id: str) -> list[dict[str, Any]]:
    conn = connection_factory(dsn)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT part_id, plan_id, name, description, quantity, unit, metadata, created_at
                FROM repair_part
                WHERE plan_id = %s
                ORDER BY created_at ASC, part_id ASC
                """,
                (plan_id,),
            )
            rows = cur.fetchall() or []
        return [_part_row_to_dict(row) for row in rows]
    finally:
        conn.close()
