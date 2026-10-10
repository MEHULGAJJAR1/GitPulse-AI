"""Raw / analytics schema DDL used by the pipeline (idempotent)."""

ANALYTICS_SCHEMA_DDL = ["CREATE SCHEMA IF NOT EXISTS analytics"]

# Mirrors app.models.RawPayload; created here so the pipeline can run standalone (Airflow worker).
# Alembic remains the source of truth in the API deployment.
RAW_TABLE_DDL = [
    "CREATE SCHEMA IF NOT EXISTS raw",
    """
    CREATE TABLE IF NOT EXISTS raw.github_payloads (
        id BIGSERIAL PRIMARY KEY,
        source_system VARCHAR(32) NOT NULL DEFAULT 'github',
        entity_type VARCHAR(32) NOT NULL,
        repo_full_name VARCHAR(200),
        natural_key VARCHAR(400) NOT NULL,
        payload JSONB NOT NULL,
        payload_hash VARCHAR(64) NOT NULL,
        run_id INTEGER,
        fetched_at TIMESTAMPTZ DEFAULT now(),
        last_seen_at TIMESTAMPTZ DEFAULT now(),
        CONSTRAINT uq_raw_payload_dedup UNIQUE (entity_type, natural_key, payload_hash)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_raw_entity_repo ON raw.github_payloads (entity_type, repo_full_name)",
]
