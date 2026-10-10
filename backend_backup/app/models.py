"""ORM models.

Schemas:
  raw        - immutable raw JSON payloads from GitHub (or the labelled synthetic fallback)
  public     - operational metadata: pipeline runs/logs, data-quality results, sync cursors,
               HTTP cache (ETag), tracked targets
  analytics  - derived staging / intermediate / mart tables built by the dbt-compatible
               SQL models (see dbt/models). Created by the transform step, not by Alembic.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class RawPayload(Base):
    """Append-only raw landing table. Dedup by (entity_type, natural_key, payload_hash)."""

    __tablename__ = "github_payloads"
    __table_args__ = (
        UniqueConstraint("entity_type", "natural_key", "payload_hash", name="uq_raw_payload_dedup"),
        {"schema": "raw"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False, default="github")
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    repo_full_name: Mapped[str | None] = mapped_column(String(200), index=True)
    natural_key: Mapped[str] = mapped_column(String(400), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    run_id: Mapped[int | None] = mapped_column(Integer)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HttpCacheEntry(Base):
    """ETag-based HTTP cache. Lets us send If-None-Match and reuse bodies on 304."""

    __tablename__ = "http_cache"

    url: Mapped[str] = mapped_column(String(700), primary_key=True)
    etag: Mapped[str | None] = mapped_column(String(200))
    body: Mapped[dict | list | None] = mapped_column(JSONB)
    next_link: Mapped[str | None] = mapped_column(String(700))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SyncState(Base):
    """Incremental-sync cursors per (target, entity)."""

    __tablename__ = "sync_state"
    __table_args__ = (UniqueConstraint("target", "entity", name="uq_sync_state"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    target: Mapped[str] = mapped_column(String(200), nullable=False)
    entity: Mapped[str] = mapped_column(String(32), nullable=False)
    cursor: Mapped[str | None] = mapped_column(String(64))
    last_page: Mapped[int | None] = mapped_column(Integer)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trigger: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)
    stage: Mapped[str | None] = mapped_column(String(32))
    targets: Mapped[list | None] = mapped_column(JSONB)
    stats: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    logs: Mapped[list[PipelineLog]] = relationship(back_populates="run", cascade="all, delete-orphan")


class PipelineLog(Base):
    __tablename__ = "pipeline_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id", ondelete="CASCADE"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    level: Mapped[str] = mapped_column(String(16), nullable=False, default="INFO")
    stage: Mapped[str | None] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text, nullable=False)

    run: Mapped[PipelineRun] = relationship(back_populates="logs")


class DataQualityResult(Base):
    __tablename__ = "data_quality_results"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id", ondelete="CASCADE"), index=True)
    check_name: Mapped[str] = mapped_column(String(120), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), default="error")
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # pass | fail | warn
    failing_rows: Mapped[int] = mapped_column(Integer, default=0)
    detail: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TrackedTarget(Base):
    """A repository, user or organisation whose public activity is ingested."""

    __tablename__ = "tracked_targets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # repo | user | org
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
