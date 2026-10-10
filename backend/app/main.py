"""GitPulse FastAPI application: middleware, routers, lifecycle (startup seeding + scheduler)."""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app import __version__
from backend.app.api import ai, analytics, dashboard, exports, pipeline, system
from backend.app.config import get_settings
from backend.app.db import get_engine
from backend.app.logging_setup import configure_logging, register_secret
from backend.app.security import SlidingWindowRateLimiter

log = logging.getLogger("gitpulse.api")


_TARGET_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,39}(/[A-Za-z0-9_.-]{1,100})?$")


def parse_target(raw: str) -> tuple[str, str] | None:
    """Normalise one DEFAULT_TARGETS entry to (kind, name). Returns None for anything not a valid GitHub target.

    Accepted: `repo:owner/name` (preferred), `user:login`, `org:login`, or a bare `owner/name` (treated as a repo)."""
    value = raw.strip()
    kind, sep, name = value.partition(":")
    if not sep:
        kind, name = "repo", value
    kind, name = kind.strip().lower(), name.strip()
    if kind not in {"repo", "user", "org"}:
        return None
    if kind == "repo" and not re.fullmatch(r"[A-Za-z0-9_.-]{1,39}/[A-Za-z0-9_.-]{1,100}", name):
        return None
    if kind != "repo" and not re.fullmatch(r"[A-Za-z0-9_.-]{1,39}", name):
        return None
    return kind, name


def _startup_housekeeping() -> None:
    """Mark runs interrupted by a restart as failed and seed default targets once."""
    s = get_settings()
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("UPDATE pipeline_runs SET status = 'failed', error = 'interrupted by service restart', "
                          "finished_at = now() WHERE status IN ('queued','running')"))
        for t in s.default_target_list:
            parsed = parse_target(t)
            if parsed is None:
                log.warning("DEFAULT_TARGETS entry ignored (expected repo:owner/name, user:name or org:name): %r", t)
                continue
            kind, name = parsed
            conn.execute(text("INSERT INTO tracked_targets (kind, name, enabled) VALUES (:k, :n, true) "
                              "ON CONFLICT (name) DO NOTHING"), {"k": kind, "n": name})


async def _scheduler(app: FastAPI, minutes: int) -> None:
    from gitpulse_elt.runner import create_run, run_pipeline
    from backend.app.services.cache import invalidate_all

    engine = get_engine()
    while True:
        await asyncio.sleep(minutes * 60)
        try:
            with engine.connect() as conn:
                busy = conn.execute(text("SELECT 1 FROM pipeline_runs WHERE status IN ('queued','running')")).first()
            if busy:
                log.info("scheduler: skipping tick, a run is in progress")
                continue
            run_id = await asyncio.to_thread(create_run, engine, "schedule", "scheduler", None, "github")
            await run_pipeline(engine, get_settings(), run_id=run_id, trigger="schedule", requested_by="scheduler")
            invalidate_all()
        except Exception:  # noqa: BLE001
            log.exception("scheduled run failed to start")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    configure_logging(s.log_level)
    for secret in (s.github_token, s.llm_api_key, s.api_keys_admin, s.api_keys_analyst, s.api_keys_viewer):
        for value in secret.split(","):
            register_secret(value.strip())
    app.state.tasks = set()
    app.state.limiter = SlidingWindowRateLimiter(s.rate_limit_per_minute)
    try:
        await asyncio.to_thread(_startup_housekeeping)
    except Exception:  # noqa: BLE001 - API must still start (health endpoint reports DB state)
        log.exception("startup housekeeping failed (is the database migrated? run: alembic upgrade head)")
    scheduler = None
    if s.pipeline_schedule_minutes > 0:
        scheduler = asyncio.create_task(_scheduler(app, s.pipeline_schedule_minutes))
        log.info("scheduler enabled: every %s minutes", s.pipeline_schedule_minutes)
    log.info("GitPulse API %s started (auth=%s, github_token=%s, llm=%s)", __version__,
             bool(s.api_keys_viewer or s.api_keys_analyst or s.api_keys_admin), bool(s.github_token), s.llm_enabled)
    yield
    if scheduler:
        scheduler.cancel()
    for task in list(app.state.tasks):
        task.cancel()


app = FastAPI(
    title="GitPulse API",
    version=__version__,
    description="GitHub activity analytics: ELT-backed metrics, statistical/ML analytics, exports and an AI assistant. "
                "All endpoints except /api/health require an API key (X-API-Key header).",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origin_list,  # explicit origins only - never "*" with credentials
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key", "Authorization"],
    expose_headers=["X-Row-Count", "X-Truncated", "X-Request-ID"],
    max_age=600,
)


@app.middleware("http")
async def security_and_rate_limit(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    started = time.monotonic()
    if request.url.path.startswith("/api/") and request.url.path != "/api/health" and request.method != "OPTIONS":
        client = request.client.host if request.client else "unknown"
        allowed, retry = request.app.state.limiter.allow(client)
        if not allowed:
            return JSONResponse({"detail": "rate limit exceeded"}, status_code=429,
                                headers={"Retry-After": str(retry), "X-Request-ID": request_id})
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = response.headers.get("Cache-Control", "no-store")
    response.headers["X-Request-ID"] = request_id
    log.info("%s %s %s %dms", request.method, request.url.path, response.status_code,
             int((time.monotonic() - started) * 1000),
             extra={"extra_fields": {"request_id": request_id, "status": response.status_code}})
    return response


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse({"detail": "invalid request", "errors": [
        {"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]}, status_code=422)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("unhandled error on %s", request.url.path)  # redacted by the logging filter
    return JSONResponse({"detail": "internal server error"}, status_code=500)


for router_module in (system, dashboard, analytics, exports, pipeline, ai):
    app.include_router(router_module.router, prefix="/api")

