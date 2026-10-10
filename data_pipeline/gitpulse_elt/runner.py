"""ELT orchestration: one function used by the API, the CLI and the Airflow DAG.

Run lifecycle (persisted in public.pipeline_runs, logs in public.pipeline_logs):
  queued -> running -> succeeded | partial | failed

Stages: extract(+load raw) -> transform (staging/intermediate/marts) -> quality -> finalize
Modes:  github (default), synthetic_seed (labelled demo fallback), synthetic_clear
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, text

from gitpulse_elt.cache import PgHttpCache
from gitpulse_elt.extract import extract_targets
from gitpulse_elt.github_client import GitHubClient
from gitpulse_elt.quality import run_checks
from gitpulse_elt.store import RawStore
from gitpulse_elt.synthetic import SYNTHETIC_SOURCE, generate
from gitpulse_elt.transform import run_transforms

log = logging.getLogger("gitpulse.runner")
DEFAULT_MODELS_DIR = Path(__file__).resolve().parents[2] / "dbt" / "models"


class RunLogger:
    LEVELS = {"INFO": logging.INFO, "WARNING": logging.WARNING, "ERROR": logging.ERROR}

    def __init__(self, engine: Engine, run_id: int):
        self.engine = engine
        self.run_id = run_id

    def __call__(self, level: str, stage: str, message: str) -> None:
        level = level.upper()
        log.log(self.LEVELS.get(level, logging.INFO), "[run %s][%s] %s", self.run_id, stage, message,
                extra={"extra_fields": {"run_id": self.run_id, "stage": stage}})
        with self.engine.begin() as conn:
            conn.execute(
                text("INSERT INTO pipeline_logs (run_id, ts, level, stage, message) VALUES (:r, now(), :l, :s, :m)"),
                {"r": self.run_id, "l": level, "s": stage, "m": message[:2000]},
            )


def create_run(engine: Engine, trigger: str, requested_by: str | None, targets: list[str] | None, mode: str) -> int:
    with engine.begin() as conn:
        return int(
            conn.execute(
                text(
                    "INSERT INTO pipeline_runs (trigger, status, targets, requested_by, created_at, stats) "
                    "VALUES (:t, 'queued', CAST(:g AS JSONB), :rb, now(), CAST(:s AS JSONB)) RETURNING id"
                ),
                {"t": trigger, "g": _json({"targets": targets or [], "mode": mode}), "rb": requested_by,
                 "s": _json({"mode": mode})},
            ).scalar_one()
        )


def _json(obj: Any) -> str:
    import json

    return json.dumps(obj, default=str)


def _set_status(engine: Engine, run_id: int, status: str, stage: str | None = None,
                error: str | None = None, stats: dict | None = None, finished: bool = False) -> None:
    """Update run status. The SET clause is built explicitly to keep bind types unambiguous."""
    sets = ["status = :status"]
    params: dict[str, Any] = {"status": status, "id": run_id}
    if stage:
        sets.append("stage = :stage")
        params["stage"] = stage
    if error:
        sets.append("error = :error")
        params["error"] = error[:4000]
    if stats:
        sets.append("stats = COALESCE(stats, '{}'::jsonb) || CAST(:stats AS JSONB)")
        params["stats"] = _json(stats)
    if status == "running":
        sets.append("started_at = COALESCE(started_at, now())")
    if finished:
        sets.append("finished_at = now()")
    with engine.begin() as conn:
        conn.execute(text(f"UPDATE pipeline_runs SET {', '.join(sets)} WHERE id = :id"), params)


def _resolve_targets(engine: Engine, settings, explicit: list[str] | None) -> list[tuple[str, str]]:
    """Explicit 'kind:name' strings, else enabled tracked_targets, else DEFAULT_TARGETS."""
    raw: list[tuple[str, str]] = []
    if explicit:
        raw = [_parse_target(t) for t in explicit]
    else:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT kind, name FROM tracked_targets WHERE enabled ORDER BY id")).all()
        raw = [(r[0], r[1]) for r in rows]
        if not raw:
            raw = [_parse_target(t) for t in settings.default_target_list]
    seen, out = set(), []
    for t in raw:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _parse_target(value: str) -> tuple[str, str]:
    if ":" in value:
        kind, name = value.split(":", 1)
    else:
        kind, name = ("repo", value)
    kind = kind.strip().lower()
    name = name.strip().strip("/")
    if kind not in {"repo", "user", "org"}:
        raise ValueError(f"invalid target kind '{kind}'")
    if kind == "repo" and (name.count("/") != 1):
        raise ValueError(f"repository target must be owner/name, got '{name}'")
    return kind, name


async def run_pipeline(
    engine: Engine,
    settings,
    *,
    run_id: int | None = None,
    trigger: str = "manual",
    requested_by: str | None = None,
    targets: list[str] | None = None,
    mode: str = "github",
    models_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute a full ELT run. Never raises for expected failures - they are recorded on the run."""
    if run_id is None:
        run_id = await asyncio.to_thread(create_run, engine, trigger, requested_by, targets, mode)
    emit = RunLogger(engine, run_id)
    started = time.monotonic()
    stats: dict[str, Any] = {"mode": mode, "trigger": trigger}
    models_dir = models_dir or DEFAULT_MODELS_DIR
    try:
        await asyncio.to_thread(_set_status, engine, run_id, "running", "start")
        store = RawStore(engine, run_id=run_id,
                         source_system=SYNTHETIC_SOURCE if mode.startswith("synthetic") else "github")
        await asyncio.to_thread(store.ensure_schema)

        status = "succeeded"
        if mode == "synthetic_seed":
            emit("WARNING", "extract", "Seeding DETERMINISTIC SYNTHETIC demo data (not live GitHub data)")
            build = generate()
            await asyncio.to_thread(store.write, build.records)
            stats["extract"] = {"synthetic_records": len(build.records), "by_entity": build.counts}
            emit("INFO", "extract", f"synthetic payloads written: {len(build.records)} (deduplicated={store.deduplicated})")
        elif mode == "synthetic_clear":
            with engine.begin() as conn:
                deleted = conn.execute(text("DELETE FROM raw.github_payloads WHERE source_system = :s"),
                                       {"s": SYNTHETIC_SOURCE}).rowcount
            emit("INFO", "extract", f"removed {deleted} synthetic raw payloads")
            stats["extract"] = {"synthetic_removed": deleted}
        else:
            if not settings.github_token:
                emit("WARNING", "extract", "GITHUB_TOKEN not set: using anonymous GitHub quota (60 req/h). "
                                           "Set GITHUB_TOKEN for higher limits and private-repo access.")
            target_list = _resolve_targets(engine, settings, targets)
            if not target_list:
                raise RuntimeError("no enabled targets: add a repository or set DEFAULT_TARGETS")
            emit("INFO", "extract", f"extracting {len(target_list)} target(s): {', '.join(n for _, n in target_list)}")
            await asyncio.to_thread(_set_status, engine, run_id, "running", "extract")
            cache = PgHttpCache(engine)
            async with GitHubClient(
                token=settings.github_token,
                base_url=settings.github_api_base,
                timeout=settings.github_timeout_seconds,
                max_retries=settings.github_max_retries,
                rate_limit_max_wait=settings.rate_limit_max_wait_seconds,
                cache=cache,
            ) as client:
                ex_stats = await extract_targets(engine=engine, client=client, store=store, settings=settings,
                                                 targets=target_list, emit=emit)
                stats["extract"] = {
                    "repos_synced": ex_stats.repos_synced, "repos_skipped": ex_stats.repos_skipped,
                    "repos_failed": ex_stats.repos_failed, "records": ex_stats.records,
                    "rate_limited": ex_stats.rate_limited, "errors": ex_stats.errors[:20],
                    "github_requests": client.stats.requests, "cache_304": client.stats.not_modified,
                    "retries": client.stats.retries, "rate_limit_waits": client.stats.rate_limit_waits,
                    "authenticated": client.authenticated, "last_remaining": client.stats.last_remaining,
                }
                if ex_stats.rate_limited or ex_stats.repos_failed:
                    status = "partial"
                if ex_stats.repos_synced == 0 and ex_stats.repos_skipped == 0:
                    status = "failed"
                    raise RuntimeError("no repositories could be extracted; see error logs")
            await asyncio.to_thread(_mark_targets, engine, target_list)

        await asyncio.to_thread(_set_status, engine, run_id, "running", "transform")
        results = await asyncio.to_thread(run_transforms, engine, models_dir, emit)
        stats["transform"] = {"models": len(results), "rows": dict(results)}

        await asyncio.to_thread(_set_status, engine, run_id, "running", "quality")
        q = await asyncio.to_thread(run_checks, engine, run_id, emit)
        stats["quality"] = q
        if q["fail"]:
            status = "partial" if status == "succeeded" else status

        stats["duration_seconds"] = round(time.monotonic() - started, 2)
        emit("INFO", "finalize", f"run finished with status '{status}' in {stats['duration_seconds']}s")
        await asyncio.to_thread(_set_status, engine, run_id, status, "finalize", None, stats, True)
        return {"run_id": run_id, "status": status, "stats": stats}
    except Exception as exc:  # noqa: BLE001 - record any failure on the run
        msg = f"{type(exc).__name__}: {exc}"
        log.exception("run %s failed", run_id)
        emit("ERROR", "pipeline", f"run failed: {msg}")
        stats["duration_seconds"] = round(time.monotonic() - started, 2)
        await asyncio.to_thread(_set_status, engine, run_id, "failed", None, msg, stats, True)
        return {"run_id": run_id, "status": "failed", "error": msg, "stats": stats}


def _mark_targets(engine: Engine, targets: list[tuple[str, str]]) -> None:
    with engine.begin() as conn:
        for kind, name in targets:
            conn.execute(text("UPDATE tracked_targets SET last_synced_at = now() WHERE name = :n"), {"n": name})


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
