# GitPulse architecture

```
GitHub REST API ──► extract (httpx, ETag cache, retries, rate-limit wait)
                        │
                        ▼
              raw.github_payloads  (immutable JSON, canonical hash dedup)
                        │
                        ▼  transform (dbt-style SQL, dependency order)
              analytics.stg_*  ──►  analytics.int_*  ──►  analytics.mart_*
                        │
                        ▼  quality checks (per run, stored)
              pipeline_runs / pipeline_logs / data_quality_results
                        │
        ┌───────────────┼──────────────────────────┐
        ▼               ▼                          ▼
 FastAPI (RBAC, rate limit)            ml_analytics (pure functions)
 dashboard · analytics · exports       forecast · anomaly · changepoint
 pipeline (SSE logs) · ai              correlation · health · clustering
        │
        ▼
 React app (TanStack Query, Recharts, Framer Motion)
```

## Key decisions

- **Raw first.** Payloads are stored unchanged, so transforms can be rebuilt without re-calling GitHub.
- **Labelled synthetic data.** Every row has `data_source`. Views filter by it and banners show it.
- **Explainable analytics.** Each insight lists its evidence and the mart it came from. Forecasts are predictions and carry intervals and backtest metrics.
- **Guardrails over guesses.** Forecasts, seasonality and clustering refuse to run below sample-size thresholds and say why.
- **Grounded assistant.** Answers are computed from marts first. An optional LLM only narrates those results.
- **Security by default.** Keys are hashed, roles are ranked, private repos are off by default, secrets are redacted, and names are validated against traversal.

## Components

| Component | Where |
|---|---|
| Auth and RBAC | `backend/app/security.py`, `backend/app/deps.py` |
| Analytics service | `backend/app/services/analytics.py`, `insights.py`, `queries.py` |
| ML modules | `ml_analytics/*.py` |
| ELT runner (CLI, scheduler entry) | `data_pipeline/gitpulse_elt/runner.py`, `__main__.py` |
| Airflow DAG | `airflow/dags/gitpulse_elt_dag.py` |
