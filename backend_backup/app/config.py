"""Typed application configuration loaded from environment variables (.env supported).

Secrets (GitHub token, API keys, LLM key) are read here only and are never returned
by any API endpoint. See `redacted_dict()` for the safe representation.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]

# Make sibling packages (ml_analytics, gitpulse_elt) importable when running from the source tree.
for _p in (REPO_ROOT, REPO_ROOT / "data_pipeline"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

SECRET_FIELDS = {"github_token", "llm_api_key", "api_keys_viewer", "api_keys_analyst", "api_keys_admin", "database_url"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(REPO_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_name: str = "GitPulse"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/gitpulse"

    # CORS / security
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    rate_limit_per_minute: int = 240

    # Auth: comma-separated API keys per role. Empty = that role unavailable.
    api_keys_viewer: str = ""
    api_keys_analyst: str = ""
    api_keys_admin: str = ""

    # GitHub
    github_token: str = ""
    github_api_base: str = "https://api.github.com"
    github_timeout_seconds: float = 20.0
    github_max_retries: int = 4
    rate_limit_max_wait_seconds: int = 90
    allow_private_repos: bool = False
    sync_lookback_days: int = 90
    commit_max_pages: int = 3
    issue_max_pages: int = 3
    pr_max_pages: int = 3
    star_max_pages: int = 5
    contributor_max_pages: int = 1
    discovery_max_repos: int = 25

    # Pipeline scheduling (0 disables in-app scheduler; Airflow DAG is the production path)
    pipeline_schedule_minutes: int = 0
    default_targets: str = Field(default="", description="Comma-separated owner/repo targets seeded on first start")
    dbt_models_dir: str = str(REPO_ROOT / "dbt" / "models")

    # Analytics
    analytics_cache_ttl_seconds: int = 300
    min_points_forecast: int = 28
    min_points_anomaly: int = 14

    # LLM (optional). Any OpenAI-compatible chat-completions endpoint works.
    llm_provider: str = "none"  # none | openai_compatible
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 30.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def default_target_list(self) -> list[str]:
        return [t.strip() for t in self.default_targets.split(",") if t.strip()]

    @property
    def llm_enabled(self) -> bool:
        return self.llm_provider != "none" and bool(self.llm_api_key)

    def redacted_dict(self) -> dict:
        out = {}
        for k, v in self.model_dump().items():
            if k in SECRET_FIELDS:
                out[k] = "***configured***" if v else "(not set)"
            else:
                out[k] = v
        return out


@lru_cache
def get_settings() -> Settings:
    return Settings()
