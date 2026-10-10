"""Raw-layer writer (the "L" of ELT).

Every GitHub object is stored as-is in raw.github_payloads (JSONB). Deduplication uses a
SHA-256 of the canonical JSON: re-ingesting an unchanged object only refreshes
`last_seen_at`; a changed object (e.g. new star count) inserts a new version. Staging
models pick the latest version per natural key.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column, DateTime, Engine, Integer, MetaData, String, Table, Text, text
from sqlalchemy.dialects.postgresql import JSONB, insert

from gitpulse_elt.schema import ANALYTICS_SCHEMA_DDL, RAW_TABLE_DDL

_md = MetaData()
RAW_PAYLOADS = Table(
    "github_payloads",
    _md,
    Column("id", Integer, primary_key=True),
    Column("source_system", String(32)),
    Column("entity_type", String(32)),
    Column("repo_full_name", String(200)),
    Column("natural_key", String(400)),
    Column("payload", JSONB),
    Column("payload_hash", String(64)),
    Column("run_id", Integer),
    Column("fetched_at", DateTime(timezone=True)),
    Column("last_seen_at", DateTime(timezone=True)),
    schema="raw",
)


def canonical_hash(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(blob).hexdigest()


@dataclass
class Record:
    entity_type: str
    natural_key: str
    repo_full_name: str | None
    payload: Any


class RawStore:
    def __init__(self, engine: Engine, run_id: int | None = None, source_system: str = "github"):
        self.engine = engine
        self.run_id = run_id
        self.source_system = source_system
        self.inserted = 0
        self.deduplicated = 0

    def ensure_schema(self) -> None:
        with self.engine.begin() as conn:
            for stmt in (*ANALYTICS_SCHEMA_DDL, *RAW_TABLE_DDL):
                conn.execute(text(stmt))

    def write(self, records: Iterable[Record]) -> int:
        rows = []
        for r in records:
            rows.append(
                {
                    "source_system": self.source_system,
                    "entity_type": r.entity_type,
                    "repo_full_name": r.repo_full_name,
                    "natural_key": r.natural_key[:400],
                    "payload": r.payload,
                    "payload_hash": canonical_hash(r.payload),
                    "run_id": self.run_id,
                    "fetched_at": datetime.now(timezone.utc),
                    "last_seen_at": datetime.now(timezone.utc),
                }
            )
        if not rows:
            return 0
        table = RAW_PAYLOADS
        stmt = insert(table).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_raw_payload_dedup",
            set_={"last_seen_at": stmt.excluded.last_seen_at, "run_id": stmt.excluded.run_id},
        )
        with self.engine.begin() as conn:
            result = conn.execute(stmt.returning(text("(xmax = 0) AS inserted")))
            flags = [bool(row[0]) for row in result]
        ins = sum(flags)
        self.inserted += ins
        self.deduplicated += len(flags) - ins
        return len(flags)
