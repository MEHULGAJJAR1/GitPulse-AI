"""Pipeline execution, job status, live logs (SSE), data-quality results and tracked targets."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text

from backend.app.config import get_settings
from backend.app.db import get_engine
from backend.app.deps import Admin, Analyst, AnyPrincipal, Conn, Viewer
from backend.app.services import queries as q
from backend.app.services.cache import invalidate_all

router = APIRouter(prefix="/pipeline")
SEGMENT_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}$")  # no leading dot: blocks '.', '..' and hidden paths
NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}(/[A-Za-z0-9_][A-Za-z0-9_.-]{0,99})?$")


def is_safe_name(value: str) -> bool:
    """Owner or owner/repo with safe path segments only."""
    parts = value.split("/")
    return 1 <= len(parts) <= 2 and all(SEGMENT_RE.match(p) for p in parts)


def is_safe_target(value: str) -> bool:
    kind, sep, name = value.partition(":")
    return bool(sep) and kind in ("repo", "user", "org") and is_safe_name(name)
FINISHED = ("succeeded", "partial", "failed")


class RunRequest(BaseModel):
    targets: list[str] | None = Field(default=None, max_length=25)
    mode: Literal["github", "synthetic_seed", "synthetic_clear"] = "github"

    @field_validator("targets")
    @classmethod
    def _valid(cls, v):
        if v is None:
            return v
        for t in v:
            if not is_safe_target(t.strip()):
                raise ValueError(f"invalid target '{t}' (expected repo:owner/name, user:login or org:login)")
        return [t.strip() for t in v]


class TargetCreate(BaseModel):
    kind: Literal["repo", "user", "org"]
    name: str = Field(min_length=1, max_length=140)

    @field_validator("name")
    @classmethod
    def _name(cls, v, info):
        v = v.strip().strip("/")
        if not is_safe_name(v):
            raise ValueError("name may contain letters, digits, '.', '-', '_' and must be owner/repo for repositories")
        return v


def _serialize(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        out[k] = v.isoformat() if isinstance(v, datetime) else v
    if out.get("started_at") and out.get("finished_at"):
        a = datetime.fromisoformat(out["started_at"])
        b = datetime.fromisoformat(out["finished_at"])
        out["duration_seconds"] = round((b - a).total_seconds(), 1)
    return out


@router.get("/status", tags=["pipeline"])
def status(principal: Viewer, conn: Conn):
    s = get_settings()
    running = q.rows(conn, "SELECT id, status, stage, created_at, started_at FROM pipeline_runs "
                           "WHERE status IN ('queued','running') ORDER BY id DESC LIMIT 1")
    last = q.recent_runs(conn, limit=1)
    targets = q.rows(conn, "SELECT count(*) FILTER (WHERE enabled) AS enabled, count(*) AS total FROM tracked_targets")
    return {
        "running": _serialize(running[0]) if running else None,
        "last_run": _serialize(last[0]) if last else None,
        "targets": targets[0] if targets else {"enabled": 0, "total": 0},
        "scheduler_minutes": s.pipeline_schedule_minutes,
        "github_token_configured": bool(s.github_token),
        "data_mode": q.data_mode(conn, principal.can_see_private),
    }


@router.get("/runs", tags=["pipeline"])
def list_runs(principal: Viewer, conn: Conn, limit: int = Query(20, ge=1, le=100)):
    return {"items": [_serialize(r) for r in q.recent_runs(conn, limit=limit)]}


@router.get("/runs/{run_id}", tags=["pipeline"])
def get_run(principal: Viewer, conn: Conn, run_id: int):
    rows = q.rows(conn, "SELECT * FROM pipeline_runs WHERE id = :id", id=run_id)
    if not rows:
        raise HTTPException(404, "run not found")
    checks = q.rows(conn, "SELECT check_name, model, severity, status, failing_rows, detail, checked_at "
                          "FROM data_quality_results WHERE run_id = :id ORDER BY id", id=run_id)
    return {"run": _serialize(rows[0]), "quality": [_serialize(c) for c in checks]}


@router.get("/runs/{run_id}/logs", tags=["pipeline"])
def run_logs(principal: Viewer, conn: Conn, run_id: int, after_id: int = Query(0, ge=0), limit: int = Query(500, ge=1, le=2000)):
    rows = q.rows(conn, "SELECT id, ts, level, stage, message FROM pipeline_logs WHERE run_id = :r AND id > :a "
                        "ORDER BY id LIMIT :l", r=run_id, a=after_id, l=limit)
    return {"items": [_serialize(r) for r in rows]}


@router.get("/runs/{run_id}/stream", tags=["pipeline"])
async def stream_run(principal: Viewer, run_id: int, request: Request):
    """Server-Sent Events: `log` for each new line, `status` on change, `end` when finished."""
    engine = get_engine()

    def snapshot(after: int):
        with engine.connect() as conn:
            run = conn.execute(text("SELECT id, status, stage, error, stats FROM pipeline_runs WHERE id = :id"),
                               {"id": run_id}).mappings().first()
            logs = conn.execute(text("SELECT id, ts, level, stage, message FROM pipeline_logs "
                                     "WHERE run_id = :r AND id > :a ORDER BY id LIMIT 500"),
                                {"r": run_id, "a": after}).mappings().all()
        return run, [_serialize(dict(l)) for l in logs]

    async def gen():
        last_id, last_status = 0, None
        idle = 0
        run = await asyncio.to_thread(lambda: snapshot(0)[0])
        if run is None:
            yield "event: error\ndata: {\"detail\": \"run not found\"}\n\n"
            return
        while True:
            if await request.is_disconnected():
                break
            run, logs = await asyncio.to_thread(snapshot, last_id)
            for line in logs:
                last_id = line["id"]
                yield f"event: log\ndata: {json.dumps(line, default=str)}\n\n"
                idle = 0
            if run and run["status"] != last_status:
                last_status = run["status"]
                payload = {"id": run["id"], "status": run["status"], "stage": run["stage"], "error": run["error"]}
                yield f"event: status\ndata: {json.dumps(payload, default=str)}\n\n"
            if run and run["status"] in FINISHED and not logs:
                yield f"event: end\ndata: {json.dumps({'id': run_id, 'status': run['status']})}\n\n"
                break
            idle += 1
            if idle % 15 == 0:
                yield ": keep-alive\n\n"
            await asyncio.sleep(1.0)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/runs", status_code=202, tags=["pipeline"])
async def start_run(request: Request, body: RunRequest, principal: AnyPrincipal):
    from gitpulse_elt.runner import create_run, run_pipeline

    if body.mode != "github" and principal.role != "admin":
        raise HTTPException(403, "synthetic demo modes require the 'admin' role")
    if body.mode == "github" and not principal.has("analyst"):
        raise HTTPException(403, "starting a pipeline run requires the 'analyst' role")
    engine = get_engine()
    with engine.connect() as conn:
        busy = conn.execute(text("SELECT id, created_at FROM pipeline_runs WHERE status IN ('queued','running') "
                                 "ORDER BY id DESC LIMIT 1")).first()
    if busy and busy[1] and busy[1] > datetime.now(timezone.utc) - timedelta(hours=6):
        raise HTTPException(409, f"pipeline run #{busy[0]} is already in progress")

    s = get_settings()
    run_id = await asyncio.to_thread(create_run, engine, "manual", principal.key_fingerprint, body.targets, body.mode)
    task = asyncio.create_task(run_pipeline(engine, s, run_id=run_id, trigger="manual",
                                            requested_by=principal.key_fingerprint, targets=body.targets, mode=body.mode))
    request.app.state.tasks.add(task)

    def _done(t):
        request.app.state.tasks.discard(t)
        invalidate_all()

    task.add_done_callback(_done)
    return {"run_id": run_id, "status": "queued", "mode": body.mode,
            "stream_url": f"/api/pipeline/runs/{run_id}/stream",
            "labelled_synthetic": body.mode != "github"}


@router.get("/quality", tags=["pipeline"])
def quality(principal: Viewer, conn: Conn):
    rows = q.rows(conn, """
        SELECT d.run_id, d.check_name, d.model, d.severity, d.status, d.failing_rows, d.detail, d.checked_at
        FROM data_quality_results d
        WHERE d.run_id = (SELECT max(run_id) FROM data_quality_results)
        ORDER BY d.id
    """)
    return {"items": [_serialize(r) for r in rows],
            "summary": {k: sum(1 for r in rows if r["status"] == k) for k in ("pass", "fail", "warn")}}


@router.get("/targets", tags=["pipeline"])
def list_targets(principal: Viewer, conn: Conn):
    rows = q.rows(conn, "SELECT id, kind, name, enabled, created_at, last_synced_at FROM tracked_targets ORDER BY id")
    return {"items": [_serialize(r) for r in rows]}


@router.post("/targets", status_code=201, tags=["pipeline"])
def create_target(body: TargetCreate, principal: Analyst):
    engine = get_engine()
    if body.kind == "repo" and body.name.count("/") != 1:
        raise HTTPException(422, "repository targets must be owner/name")
    if body.kind != "repo" and "/" in body.name:
        raise HTTPException(422, "user and org targets must be a login without '/'")
    name = body.name
    with engine.begin() as conn:
        exists = conn.execute(text("SELECT id FROM tracked_targets WHERE name = :n"), {"n": name}).first()
        if exists:
            raise HTTPException(409, "target already tracked")
        new_id = conn.execute(text("INSERT INTO tracked_targets (kind, name, enabled) VALUES (:k, :n, true) RETURNING id"),
                              {"k": body.kind, "n": name}).scalar_one()
    return {"id": new_id, "kind": body.kind, "name": name, "enabled": True}


@router.patch("/targets/{target_id}", tags=["pipeline"])
def toggle_target(target_id: int, principal: Analyst, enabled: bool = Query(...)):
    with get_engine().begin() as conn:
        res = conn.execute(text("UPDATE tracked_targets SET enabled = :e WHERE id = :i"), {"e": enabled, "i": target_id})
        if res.rowcount == 0:
            raise HTTPException(404, "target not found")
    return {"id": target_id, "enabled": enabled}


@router.delete("/targets/{target_id}", status_code=204, tags=["pipeline"])
def delete_target(target_id: int, principal: Admin):
    with get_engine().begin() as conn:
        res = conn.execute(text("DELETE FROM tracked_targets WHERE id = :i"), {"i": target_id})
        if res.rowcount == 0:
            raise HTTPException(404, "target not found")
    return None

