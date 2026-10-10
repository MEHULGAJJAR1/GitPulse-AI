# GitPulse

GitPulse ingests GitHub activity through the official REST API, lands raw JSON, models it with dbt-style SQL,
checks data quality, and serves explainable analytics (descriptive, diagnostic, trend, comparative, predictive)
through a FastAPI backend and a React dashboard. An AI assistant answers questions from database results.

> **Data honesty.** Repositories are labelled `github` (live REST data) or `synthetic` (deterministic demo data
> produced by `--mode synthetic_seed`). The UI shows the data mode on every page. Synthetic data is never presented as
> GitHub activity.

## Repository layout

| Path | Purpose |
|---|---|
| `backend/` | FastAPI app, SQLAlchemy models, Alembic migrations, RBAC, rate limiting, SSE, AI assistant |
| `data_pipeline/gitpulse_elt/` | GitHub client (pagination, ETag cache, retries, rate limits), extract, load, transform, quality, runner CLI |
| `ml_analytics/` | Forecasting with backtests, anomaly detection, change points, seasonality, correlation, health score, guarded clustering |
| `dbt/` | Staging, intermediate and mart SQL models, schema tests |
| `airflow/dags/` | Airflow DAG (extract → transform → quality) |
| `frontend/` | React + TypeScript + Vite + Tailwind + Recharts + Framer Motion |
| `tests/` | Unit, ML evaluation, data-quality, and live API tests (frontend tests live in `frontend/src/__tests__`) |
| `scripts/` | Setup, run and test scripts for Windows PowerShell and macOS/Linux |
| `docs/` | Architecture notes |

## Prerequisites

- Python 3.13 (3.11+ should work)
- Node.js 20 or newer, with npm
- PostgreSQL 14 or newer (local install, or Docker)
- Optional: a GitHub token (fine-grained, read-only, public repositories). Without one, GitHub allows 60 requests per hour.
- Optional: Docker Desktop for the container stack.

## Quick start: Windows (PowerShell)

```powershell
# 1. Create the database (adjust user/password to your PostgreSQL install)
psql -U postgres -c "CREATE DATABASE gitpulse;"

# 2. Set up Python, Node, .env (generates API keys), migrations and the frontend build
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -SeedDemo

# 3. Edit .env: set DATABASE_URL, and optionally GITHUB_TOKEN and DEFAULT_TARGETS

# 4. Ingest real GitHub repositories (analyst or admin role is needed through the API; this CLI runs as the operator)
cd data_pipeline
..\.venv\Scripts\python.exe -m gitpulse_elt run --target repo:octocat/Hello-World --target repo:pallets/click
cd ..

# 5. Start the API and the web app in two terminals
.\scripts\run.ps1 api       # http://localhost:8000/api/docs
.\scripts\run.ps1 web       # http://localhost:5173
```

## Quick start: macOS / Linux

```bash
# 1. Create the database
createdb gitpulse            # or: psql -U postgres -c "CREATE DATABASE gitpulse;"

# 2. Setup (creates .venv, .env with generated keys, runs migrations, builds the frontend)
chmod +x scripts/*.sh
./scripts/setup.sh --seed-demo

# 3. Edit .env: DATABASE_URL, and optionally GITHUB_TOKEN and DEFAULT_TARGETS

# 4. Ingest real GitHub repositories
cd data_pipeline && ../.venv/bin/python -m gitpulse_elt run --target repo:octocat/Hello-World --target repo:pallets/click && cd ..

# 5. Start the API and the web app
./scripts/run.sh api         # http://localhost:8000/api/docs
./scripts/run.sh web         # http://localhost:5173
```

Sign in at the web app with the `API_KEYS_ADMIN` value from `.env` (viewer and analyst keys are also generated).

## Docker

```bash
cp .env.example .env         # then set POSTGRES_PASSWORD and the API keys
docker compose up -d --build
# Web app: http://localhost:8080   API docs: http://localhost:8080/api/docs
```

PowerShell is the same, with `Copy-Item .env.example .env`.

## Roles and security

| Role | Can do |
|---|---|
| `viewer` | Read dashboards, analytics, exports, assistant |
| `analyst` | Also manage tracked targets and start GitHub ingestion runs |
| `admin` | Also seed or clear labelled synthetic data, delete targets, view redacted configuration |

- API keys are sent in the `X-API-Key` header. The server stores only SHA-256 digests and compares them in constant time.
- Private repositories are hidden from non-privileged roles and are off by default (`ALLOW_PRIVATE_REPOS=false`).
- Per-IP sliding-window rate limit (`RATE_LIMIT_PER_MINUTE`), CORS allowlist (`CORS_ORIGINS`), strict input validation (owner/repo names reject `..` and leading dots), secret redaction in logs and `/api/admin/config`.
- The nginx image sets CSP, `X-Frame-Options: DENY`, and `nosniff`.

## Pipeline

1. **Extract** (`extract.py`, `github_client.py`): repositories, commits, contributors, issues, pull requests, branches, releases, stargazers. Pagination via `Link`, ETag/conditional requests cached in Postgres, retries with backoff, `Retry-After` and `X-RateLimit-Reset` handling, and a maximum wait so a run fails cleanly instead of hanging.
2. **Land raw** (`store.py`): immutable JSON payloads with canonical hashes for deduplication.
3. **Transform** (`transform.py`): dbt-style SQL in dependency order (staging → intermediate → marts), also usable through dbt.
4. **Quality** (`quality.py`): uniqueness, not-null, accepted-values and reconciliation checks. Results are stored per run.
5. **Schedule**: in-app scheduler (`PIPELINE_SCHEDULE_MINUTES`) or the Airflow DAG `airflow/dags/gitpulse_elt_dag.py`.

Every run has a history row, log lines streamed over Server-Sent Events (`/api/pipeline/runs/{id}/stream`), and quality results.

## Analytics

- **Descriptive**: totals, averages, medians, distributions, moving averages.
- **Trend and seasonality**: linear trend with p-value; weekday profile, only when data is sufficient.
- **Forecasts**: Holt smoothing with 80% and 95% intervals and a holdout backtest against a naive baseline. Forecasts are labelled as predictions and withheld when history is too short.
- **Anomalies**: robust z-score (median/MAD), with Isolation Forest corroboration where history allows.
- **Change points**: binary segmentation with Welch t-tests.
- **Correlation**: Pearson and Spearman, labelled as association, not causation.
- **Health score**: weighted components with explanations and data-gap reporting.
- **Clustering**: k-means on repository activity, refused below a minimum repository count. Clusters are similarity groups, not quality rankings.

## Tests

```bash
./scripts/test.sh               # macOS/Linux
.\scripts\test.ps1              # Windows
```

| Layer | Location | What it checks |
|---|---|---|
| Unit | `tests/unit` | RBAC resolution, rate limiter, secret redaction, GitHub pagination and rate-limit helpers |
| ML evaluation | `tests/ml` | Forecast refusal on thin data, interval ordering, forecast vs. naive baseline, injected anomaly and change-point recovery, quiet on noise |
| Data quality | `tests/dq` | Check catalogue is well formed; live checks on the latest run when `GITPULSE_DQ_LIVE=1` |
| API | `tests/api` | Live server: auth, data-mode labels, target-name rejection, RBAC on runs, grounded AI answers, export metadata |
| Frontend | `frontend/src/__tests__` | Formatting, API client auth header, data-mode labelling, login flow, heatmap/correlation rendering, no hardcoded demo data |
| Build | `frontend` | `tsc --noEmit` and `vite build` |

API tests skip automatically when the server is down.

## Configuration

See `.env.example` for every variable. The important ones:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLAlchemy URL, `postgresql+psycopg://user:pass@host:5432/gitpulse` |
| `API_KEYS_VIEWER` / `_ANALYST` / `_ADMIN` | Comma-separated keys per role |
| `GITHUB_TOKEN` | Raises GitHub limits; never shown in the UI or logs |
| `DEFAULT_TARGETS` | Comma-separated targets seeded on first start, e.g. `repo:octocat/Hello-World,repo:pallets/click` (`user:`/`org:` also accepted; invalid entries are logged and skipped) |
| `PIPELINE_SCHEDULE_MINUTES` | In-app schedule; `0` disables it |
| `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` | Optional OpenAI-compatible narration. Without it, the rule-based assistant is used |

## Known limitations

- The rate limiter is per process. Use Redis for multiple API replicas.
- Without `GITHUB_TOKEN`, a full sync of several repositories can exhaust the anonymous quota within an hour. The pipeline stops and records the reason.
- Forecasts and anomaly results depend on history length. Repositories with little history show "insufficient data" by design.
- LLM narration needs your own provider key. The assistant's answers are grounded in database results either way.

## Troubleshooting

- **`401 invalid API key`**: use a key from `.env` exactly (no quotes, no spaces).
- **Run fails with "rate limit"**: add `GITHUB_TOKEN` to `.env`, restart the API, and re-run.
- **Frontend shows "Could not reach"**: check that the API is running on port 8000. The Vite dev server proxies `/api`.
- **Port in use**: change the port in `scripts/run.*` and `frontend/vite.config.ts`.
