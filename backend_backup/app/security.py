"""Authentication (API keys per role), RBAC, and an in-memory per-IP rate limiter.

Roles (ascending privilege): viewer < analyst < admin.
  viewer  - read dashboards, analytics, exports of public data
  analyst - + trigger pipeline runs, manage tracked targets, private repos (if enabled), AI assistant
  admin   - + demo-data management, configuration view

Keys are compared in constant time against SHA-256 digests; raw keys are never logged.
"""

from __future__ import annotations

import hashlib
import hmac
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request, status

from app.config import Settings, get_settings

ROLE_RANK = {"viewer": 1, "analyst": 2, "admin": 3}


@dataclass(frozen=True)
class Principal:
    role: str
    key_fingerprint: str

    def has(self, min_role: str) -> bool:
        return ROLE_RANK[self.role] >= ROLE_RANK[min_role]

    @property
    def can_see_private(self) -> bool:
        return self.has("analyst") and get_settings().allow_private_repos


def _split(value: str) -> list[str]:
    return [k.strip() for k in value.split(",") if k.strip()]


def _key_table(settings: Settings) -> list[tuple[str, str]]:
    table: list[tuple[str, str]] = []
    for role, raw in (
        ("admin", settings.api_keys_admin),
        ("analyst", settings.api_keys_analyst),
        ("viewer", settings.api_keys_viewer),
    ):
        table.extend((hashlib.sha256(k.encode()).hexdigest(), role) for k in _split(raw))
    return table


def resolve_role(presented: str | None, settings: Settings | None = None) -> Principal | None:
    if not presented:
        return None
    settings = settings or get_settings()
    digest = hashlib.sha256(presented.encode()).hexdigest()
    matched: Principal | None = None
    for known_digest, role in _key_table(settings):
        if hmac.compare_digest(known_digest, digest):
            matched = Principal(role=role, key_fingerprint=digest[:8])
    return matched


def get_principal(
    x_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> Principal:
    presented = x_api_key
    if not presented and authorization and authorization.lower().startswith("bearer "):
        presented = authorization.split(" ", 1)[1].strip()
    settings = get_settings()
    if not _key_table(settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured. Run the setup script or set GITPULSE_API_KEYS in .env.",
        )
    principal = resolve_role(presented, settings)
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid API key")
    return principal


def require_role(min_role: str):
    def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if not principal.has(min_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires the '{min_role}' role (you are '{principal.role}')",
            )
        return principal

    return dependency


class SlidingWindowRateLimiter:
    """Per-client-IP sliding window. Suitable for a single process; use Redis for scale-out."""

    def __init__(self, limit_per_minute: int):
        self.limit = limit_per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, client_id: str) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            window = self._hits[client_id]
            while window and now - window[0] > 60:
                window.popleft()
            if len(window) >= self.limit:
                retry_after = int(60 - (now - window[0])) + 1
                return False, retry_after
            window.append(now)
            return True, 0
