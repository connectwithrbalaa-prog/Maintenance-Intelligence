from dataclasses import dataclass
from typing import Iterable, Optional

ROLE_ORDER = {"viewer": 0, "operator": 1, "admin": 2}


@dataclass(frozen=True)
class TenantContext:
    org_id: str
    role: str
    subject: str = "anonymous"


def normalize_role(role: str) -> str:
    role = (role or "viewer").strip().lower()
    if role not in ROLE_ORDER:
        raise ValueError(f"Unsupported role: {role}")
    return role


def role_allows(role: str, minimum_role: str) -> bool:
    return ROLE_ORDER[normalize_role(role)] >= ROLE_ORDER[normalize_role(minimum_role)]


def resolve_org_id(settings, org_id: Optional[str] = None) -> str:
    return org_id or getattr(settings, "default_org", "default-org")


def org_scope_enabled(settings) -> bool:
    return bool(getattr(settings, "multi_tenant", False))


def scoped_topic(base_topic: str, settings, org_id: Optional[str] = None) -> str:
    if not org_scope_enabled(settings) or getattr(settings, "kafka_tenant_mode", "message") != "namespaced":
        return base_topic
    parts = base_topic.split(".")
    if len(parts) < 2:
        return base_topic
    effective_org = resolve_org_id(settings, org_id)
    return ".".join([parts[0], effective_org, *parts[1:]])


def consumer_topics(base_topics: Iterable[str], settings, org_id: Optional[str] = None) -> list[str]:
    return [scoped_topic(topic, settings, org_id=org_id) for topic in base_topics]


def event_in_scope(message_org_id: Optional[str], settings, org_id: Optional[str] = None) -> bool:
    if not org_scope_enabled(settings):
        return True
    return (message_org_id or resolve_org_id(settings)) == resolve_org_id(settings, org_id)
