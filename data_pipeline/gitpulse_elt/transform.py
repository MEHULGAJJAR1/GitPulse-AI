"""Transform stage: executes the dbt model SQL in dependency order.

The SQL files under dbt/models are valid dbt models (they use {{ ref() }}, {{ source() }}
and {{ config() }}). This module renders the same Jinja subset that dbt would, so the
pipeline can run without a dbt installation (e.g. in a slim worker). When dbt is installed
you can instead run `dbt build` from dbt/ - both paths produce identical analytics.* tables.

Layers: staging (stg_*) -> intermediate (int_*) -> marts (mart_*).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from graphlib import TopologicalSorter
from pathlib import Path

from sqlalchemy import Engine, text

log = logging.getLogger("gitpulse.transform")

_REF = re.compile(r"\{\{\s*ref\(\s*'([^']+)'\s*\)\s*\}\}")
_SOURCE = re.compile(r"\{\{\s*source\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)\s*\}\}")
_CONFIG = re.compile(r"\{\{\s*config\([^}]*\)\s*\}\}")


@dataclass(frozen=True)
class Model:
    name: str
    layer: str
    path: Path
    sql: str  # raw dbt SQL
    deps: frozenset[str]


def render(sql: str) -> str:
    """Render the dbt Jinja subset used by our models into plain PostgreSQL."""
    sql = _CONFIG.sub("", sql)
    sql = _SOURCE.sub(lambda m: f"{m.group(1)}.{m.group(2)}", sql)
    sql = _REF.sub(lambda m: f"analytics.{m.group(1)}", sql)
    return sql.strip().rstrip(";")


def discover_models(models_dir: Path) -> dict[str, Model]:
    models: dict[str, Model] = {}
    for path in sorted(models_dir.rglob("*.sql")):
        raw = path.read_text(encoding="utf-8")
        deps = frozenset(_REF.findall(raw))
        layer = path.parent.name
        name = path.stem
        if name in models:
            raise ValueError(f"duplicate model name {name}")
        models[name] = Model(name=name, layer=layer, path=path, sql=raw, deps=deps)
    return models


def execution_order(models: dict[str, Model]) -> list[str]:
    graph = {name: {d for d in m.deps if d in models} for name, m in models.items()}
    unknown = {d for m in models.values() for d in m.deps if d not in models}
    if unknown:
        raise ValueError(f"models reference unknown refs: {sorted(unknown)}")
    return list(TopologicalSorter(graph).static_order())


def run_transforms(engine: Engine, models_dir: Path, emit=None) -> list[tuple[str, int]]:
    """Materialise every model as a table in the analytics schema. Returns (model, rows)."""
    emit = emit or (lambda level, stage, msg: log.info("%s %s", stage, msg))
    models = discover_models(models_dir)
    order = execution_order(models)
    results: list[tuple[str, int]] = []
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS analytics"))
    for name in order:
        model = models[name]
        body = render(model.sql)
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS analytics.{name} CASCADE"))
            conn.execute(text(f"CREATE TABLE analytics.{name} AS {body}"))
            rows = conn.execute(text(f"SELECT count(*) FROM analytics.{name}")).scalar_one()
        results.append((name, int(rows)))
        emit("INFO", "transform", f"built {model.layer}/{name}: {rows} rows")
    return results
