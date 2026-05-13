from __future__ import annotations

from dataclasses import dataclass
import hashlib
import time
from uuid import uuid4

from app.core.config import settings
from app.models.ops import AuthPrincipal, AutonomyLevel, Role


ROLE_RANK: dict[Role, int] = {
    "anonymous": 0,
    "viewer": 1,
    "analyst": 2,
    "admin": 3,
    "super_admin": 4,
}


@dataclass(frozen=True)
class EndpointRule:
    method: str
    prefix: str
    role: Role
    risk_level: AutonomyLevel
    approval_required: bool = False


ENDPOINT_RULES: tuple[EndpointRule, ...] = (
    EndpointRule("GET", "/ops", "analyst", "level_0"),
    EndpointRule("POST", "/products/canonical-merge-preview", "analyst", "level_0"),
    EndpointRule("POST", "/products/", "admin", "level_1"),
    EndpointRule("POST", "/ops/autonomy-queue", "admin", "level_1"),
    EndpointRule("GET", "/approvals", "analyst", "level_0"),
    EndpointRule("GET", "/health/workers", "analyst", "level_0"),
    EndpointRule("GET", "/health/external-sources", "analyst", "level_0"),
    EndpointRule("GET", "/sources/product-url/known", "analyst", "level_0"),
    EndpointRule("POST", "/pricing/refresh", "analyst", "level_0"),
    EndpointRule("POST", "/pricing/canonicalize", "analyst", "level_0"),
    EndpointRule("POST", "/sources/product-url/preview", "analyst", "level_0"),
    EndpointRule("POST", "/sources/product-url/ingest", "admin", "level_1"),
    EndpointRule("POST", "/sources/product-url/refresh", "admin", "level_1"),
    EndpointRule("POST", "/pricing/sync", "admin", "level_1"),
    EndpointRule("POST", "/pricing/discover", "admin", "level_1"),
    EndpointRule("POST", "/telemetry/ingest", "analyst", "level_1"),
    EndpointRule("POST", "/telemetry/products", "analyst", "level_1"),
    EndpointRule("POST", "/intelligence", "analyst", "level_1"),
    EndpointRule("POST", "/cognition", "analyst", "level_1"),
    EndpointRule("POST", "/governance/refresh", "analyst", "level_1"),
    EndpointRule("POST", "/alignment/refresh", "analyst", "level_1"),
    EndpointRule("POST", "/autonomy/events", "analyst", "level_1"),
    EndpointRule("POST", "/autonomy/run", "admin", "level_1"),
    EndpointRule("POST", "/evolution/refresh", "analyst", "level_1"),
    EndpointRule("POST", "/evolution/policies", "super_admin", "level_2", True),
    EndpointRule("POST", "/evolution/rollback", "super_admin", "level_2", True),
    EndpointRule("POST", "/approvals", "admin", "level_2", True),
)


class RateLimiter:
    def __init__(self, *, window_seconds: int = 60, max_requests: int = 120) -> None:
        self.window_seconds = window_seconds
        self.max_requests = max_requests
        self._buckets: dict[str, tuple[float, int]] = {}

    def allow(self, key: str) -> bool:
        now = time.time()
        started_at, count = self._buckets.get(key, (now, 0))
        if now - started_at >= self.window_seconds:
            self._buckets[key] = (now, 1)
            return True
        if count >= self.max_requests:
            return False
        self._buckets[key] = (started_at, count + 1)
        return True


def configured_key_map() -> dict[str, Role]:
    key_map: dict[str, Role] = {}
    for key, role in (
        (settings.viewer_api_key, "viewer"),
        (settings.analyst_api_key, "analyst"),
        (settings.admin_api_key, "admin"),
        (settings.super_admin_api_key, "super_admin"),
    ):
        if key:
            key_map[key] = role  # type: ignore[assignment]
    return key_map


def authenticate_api_key(api_key: str | None, key_map: dict[str, Role] | None = None) -> AuthPrincipal:
    if not settings.auth_required:
        return AuthPrincipal(actor="local-dev", role="super_admin", authenticated=True)
    if not api_key:
        return AuthPrincipal()
    role = (key_map or configured_key_map()).get(api_key)
    if not role:
        return AuthPrincipal()
    return AuthPrincipal(actor=f"{role}:api-key", role=role, authenticated=True)


def has_role(principal: AuthPrincipal, required: Role) -> bool:
    return ROLE_RANK[principal.role] >= ROLE_RANK[required]


def endpoint_rule(method: str, path: str) -> EndpointRule | None:
    method = method.upper()
    for rule in ENDPOINT_RULES:
        if method == rule.method and path.startswith(rule.prefix):
            return rule
    return None


def payload_hash(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def trace_id() -> str:
    return f"trace-{uuid4()}"
