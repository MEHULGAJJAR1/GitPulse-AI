"""Health, identity and administrative configuration endpoints."""

from fastapi import APIRouter

from backend.app import __version__
from backend.app.config import get_settings
from backend.app.db import ping
from backend.app.deps import AnyPrincipal, Admin
from backend.app.services.llm import llm_status

router = APIRouter()


@router.get("/health", tags=["system"])
def health():
    """Liveness + dependency status. Public and secret-free."""
    s = get_settings()
    db_ok = ping()
    return {
        "status": "ok" if db_ok else "degraded",
        "version": __version__,
        "database": "up" if db_ok else "down",
        "github_token_configured": bool(s.github_token),
        "llm": llm_status(),
        "auth_configured": bool(s.api_keys_viewer or s.api_keys_analyst or s.api_keys_admin),
        "scheduler_minutes": s.pipeline_schedule_minutes,
    }


@router.get("/me", tags=["system"])
def me(principal: AnyPrincipal):
    s = get_settings()
    return {
        "role": principal.role,
        "can_see_private_repos": principal.can_see_private,
        "private_repos_enabled": s.allow_private_repos,
        "llm": llm_status(),
    }


@router.get("/admin/config", tags=["system"])
def admin_config(_: Admin):
    """Configuration with every secret masked."""
    return get_settings().redacted_dict()

