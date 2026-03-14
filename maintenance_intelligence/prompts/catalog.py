import hashlib
from typing import Any, Dict, List, Optional

from maintenance_intelligence.context.assembler import with_pg
from maintenance_intelligence.runner.config import Settings

DEFAULT_PROMPTS: List[Dict[str, Any]] = [
    {
        "prompt_id": "rca-default-v1",
        "route_name": "rca",
        "version": 1,
        "description": "Conservative RCA prompt for general industrial alarms.",
        "intended_use": {"severity": ["medium", "high"], "asset_class": ["pump", "compressor", "generic"]},
        "system_prompt": "You are an industrial maintenance RCA assistant. Be concise, operational, and evidence-driven.",
        "user_prompt_template": (
            "Return strict JSON only with title, hypothesis, evidence_ids, immediate_actions, pm_suggestions, confidence.\n"
            "Event: {event_json}\nContext: {context_json}\n"
            "Prefer operationally safe actions first."
        ),
        "active": True,
    },
    {
        "prompt_id": "rca-canary-v1",
        "route_name": "rca",
        "version": 1,
        "description": "Canary RCA prompt biased toward faster synthesis and actionability.",
        "intended_use": {"severity": ["high"], "asset_class": ["pump", "compressor"]},
        "system_prompt": "You are an industrial maintenance RCA assistant. Prioritize the most probable failure mode and immediate mitigation steps.",
        "user_prompt_template": (
            "Return strict JSON only with title, hypothesis, evidence_ids, immediate_actions, pm_suggestions, confidence.\n"
            "Event: {event_json}\nContext: {context_json}\n"
            "Bias toward the most actionable next steps for severity={severity}, kind={kind}."
        ),
        "active": True,
    },
]


def _subject_bucket(subject_key: str) -> float:
    digest = hashlib.sha256(subject_key.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _acceptance_rate(stats: Dict[str, Any]) -> float:
    total = float(stats.get("total", 0) or 0)
    accept = float(stats.get("accept", 0) or 0)
    return (accept / total) if total > 0 else 0.0


def choose_prompt_variant(
    prompts_by_id: Dict[str, Dict[str, Any]],
    route_config: Dict[str, Any],
    subject_key: str,
    feedback_stats: Optional[Dict[str, Dict[str, Any]]] = None,
    subject_bucket: Optional[float] = None,
) -> Dict[str, Any]:
    default_prompt_id = route_config.get("default_prompt_id")
    canary_prompt_id = route_config.get("canary_prompt_id")
    canary_ratio = float(route_config.get("canary_ratio") or 0.0)
    auto_rollback_triggered = False

    if canary_prompt_id and route_config.get("auto_rollback_enabled") and feedback_stats:
        min_runs = int(route_config.get("rollback_min_runs") or 20)
        acceptance_delta = float(route_config.get("rollback_acceptance_delta") or 0.05)
        default_stats = feedback_stats.get(default_prompt_id, {})
        canary_stats = feedback_stats.get(canary_prompt_id, {})
        if default_stats.get("total", 0) >= min_runs and canary_stats.get("total", 0) >= min_runs:
            if _acceptance_rate(canary_stats) + acceptance_delta < _acceptance_rate(default_stats):
                auto_rollback_triggered = True
                canary_prompt_id = None

    bucket = subject_bucket if subject_bucket is not None else _subject_bucket(subject_key)
    selected_prompt_id = default_prompt_id
    variant = "default"
    if canary_prompt_id and canary_ratio > 0 and bucket < canary_ratio:
        selected_prompt_id = canary_prompt_id
        variant = "canary"

    prompt = prompts_by_id[selected_prompt_id]
    return {
        "prompt": prompt,
        "prompt_id": selected_prompt_id,
        "variant": variant,
        "route_name": route_config.get("route_name"),
        "auto_rollback_triggered": auto_rollback_triggered,
    }


def _default_route_config(settings: Settings, route_name: str, org_id: str) -> Dict[str, Any]:
    default_prompt_id = settings.prompt_defaults.get(route_name, f"{route_name}-default-v1")
    return {
        "config_id": f"{org_id}:{route_name}",
        "org_id": org_id,
        "route_name": route_name,
        "default_prompt_id": default_prompt_id,
        "canary_prompt_id": settings.prompt_canary_defaults.get(route_name),
        "canary_ratio": float(settings.prompt_canary_ratio or 0.0),
        "auto_rollback_enabled": True,
        "rollback_min_runs": 20,
        "rollback_acceptance_delta": 0.05,
    }


def seed_prompt_catalog(conn) -> None:
    with conn, conn.cursor() as cur:
        for prompt in DEFAULT_PROMPTS:
            cur.execute(
                """
                INSERT INTO prompt_catalog (
                    prompt_id, route_name, version, description, intended_use, system_prompt, user_prompt_template, active
                )
                VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s)
                ON CONFLICT (prompt_id) DO NOTHING
                """,
                (
                    prompt["prompt_id"],
                    prompt["route_name"],
                    prompt["version"],
                    prompt["description"],
                    __import__("json").dumps(prompt["intended_use"]),
                    prompt["system_prompt"],
                    prompt["user_prompt_template"],
                    prompt["active"],
                ),
            )


def list_prompts(conn, route_name: str | None = None) -> List[Dict[str, Any]]:
    seed_prompt_catalog(conn)
    with conn, conn.cursor() as cur:
        if route_name:
            cur.execute(
                """
                SELECT prompt_id, route_name, version, description, intended_use, system_prompt, user_prompt_template, active
                FROM prompt_catalog
                WHERE route_name = %s
                ORDER BY route_name, version DESC, prompt_id
                """,
                (route_name,),
            )
        else:
            cur.execute(
                """
                SELECT prompt_id, route_name, version, description, intended_use, system_prompt, user_prompt_template, active
                FROM prompt_catalog
                ORDER BY route_name, version DESC, prompt_id
                """
            )
        rows = cur.fetchall() or []
    return [
        {
            "prompt_id": row[0],
            "route_name": row[1],
            "version": row[2],
            "description": row[3],
            "intended_use": row[4] or {},
            "system_prompt": row[5],
            "user_prompt_template": row[6],
            "active": row[7],
        }
        for row in rows
    ]


def load_route_config(conn, settings: Settings, route_name: str, org_id: str) -> Dict[str, Any]:
    seed_prompt_catalog(conn)
    config_ids = [f"{org_id}:{route_name}", f"global:{route_name}"]
    with conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT config_id, org_id, route_name, default_prompt_id, canary_prompt_id, canary_ratio,
                   auto_rollback_enabled, rollback_min_runs, rollback_acceptance_delta
            FROM prompt_route_configs
            WHERE config_id = ANY(%s)
            ORDER BY CASE WHEN config_id = %s THEN 0 ELSE 1 END
            LIMIT 1
            """,
            (config_ids, f"{org_id}:{route_name}"),
        )
        row = cur.fetchone()
    if not row:
        return _default_route_config(settings, route_name, org_id)
    return {
        "config_id": row[0],
        "org_id": row[1],
        "route_name": row[2],
        "default_prompt_id": row[3],
        "canary_prompt_id": row[4],
        "canary_ratio": float(row[5] or 0.0),
        "auto_rollback_enabled": bool(row[6]),
        "rollback_min_runs": int(row[7] or 20),
        "rollback_acceptance_delta": float(row[8] or 0.05),
    }


def save_route_config(conn, route_name: str, org_id: Optional[str], payload: Dict[str, Any]) -> Dict[str, Any]:
    seed_prompt_catalog(conn)
    effective_org = org_id or "global"
    config_id = f"{effective_org}:{route_name}"
    with conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO prompt_route_configs (
                config_id, org_id, route_name, default_prompt_id, canary_prompt_id, canary_ratio,
                auto_rollback_enabled, rollback_min_runs, rollback_acceptance_delta
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (config_id) DO UPDATE SET
                default_prompt_id = EXCLUDED.default_prompt_id,
                canary_prompt_id = EXCLUDED.canary_prompt_id,
                canary_ratio = EXCLUDED.canary_ratio,
                auto_rollback_enabled = EXCLUDED.auto_rollback_enabled,
                rollback_min_runs = EXCLUDED.rollback_min_runs,
                rollback_acceptance_delta = EXCLUDED.rollback_acceptance_delta,
                updated_at = NOW()
            """,
            (
                config_id,
                None if effective_org == "global" else effective_org,
                route_name,
                payload["default_prompt_id"],
                payload.get("canary_prompt_id"),
                float(payload.get("canary_ratio") or 0.0),
                bool(payload.get("auto_rollback_enabled", True)),
                int(payload.get("rollback_min_runs") or 20),
                float(payload.get("rollback_acceptance_delta") or 0.05),
            ),
        )
    return {
        "config_id": config_id,
        "org_id": None if effective_org == "global" else effective_org,
        "route_name": route_name,
        "default_prompt_id": payload["default_prompt_id"],
        "canary_prompt_id": payload.get("canary_prompt_id"),
        "canary_ratio": float(payload.get("canary_ratio") or 0.0),
        "auto_rollback_enabled": bool(payload.get("auto_rollback_enabled", True)),
        "rollback_min_runs": int(payload.get("rollback_min_runs") or 20),
        "rollback_acceptance_delta": float(payload.get("rollback_acceptance_delta") or 0.05),
    }


def prompt_feedback_stats(conn, org_id: str, prompt_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    if not prompt_ids:
        return {}
    with conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT prompt_id,
                   COUNT(*) AS total_count,
                   COUNT(*) FILTER (WHERE action = 'accept') AS accept_count
            FROM rca_feedback
            WHERE org_id = %s AND prompt_id = ANY(%s)
            GROUP BY prompt_id
            """,
            (org_id, prompt_ids),
        )
        rows = cur.fetchall() or []
    return {row[0]: {"total": int(row[1] or 0), "accept": int(row[2] or 0)} for row in rows}


def resolve_prompt_for_route(
    route_name: str,
    org_id: str,
    subject_key: str,
    settings: Optional[Settings] = None,
) -> Dict[str, Any]:
    settings = settings or Settings()
    fallback_prompts = {prompt["prompt_id"]: prompt for prompt in DEFAULT_PROMPTS if prompt["route_name"] == route_name}
    fallback_config = _default_route_config(settings, route_name, org_id)
    try:
        conn = with_pg(settings.pg_dsn)
    except Exception:
        return choose_prompt_variant(fallback_prompts, fallback_config, subject_key)

    try:
        prompts = list_prompts(conn, route_name=route_name)
        prompts_by_id = {prompt["prompt_id"]: prompt for prompt in prompts}
        route_config = load_route_config(conn, settings, route_name, org_id)
        stats = prompt_feedback_stats(
            conn,
            org_id,
            [prompt_id for prompt_id in [route_config.get("default_prompt_id"), route_config.get("canary_prompt_id")] if prompt_id],
        )
        return choose_prompt_variant(prompts_by_id, route_config, subject_key, feedback_stats=stats)
    finally:
        conn.close()