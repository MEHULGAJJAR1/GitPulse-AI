# Windows fix runbook (D:\Project\gitpulse)

Apply the changed files listed below, then run these PowerShell commands from `D:\Project\gitpulse`.

## Changed files (copy into the same relative paths)
Backend
- backend/app/services/queries.py: `needs_analytics` guard; contributor ranking merges commit-window and all-time GitHub contributions (`basis`); private-repo filter on repo contributors; unattributed `unknown` logins excluded.
- backend/app/api/dashboard.py: overview uses guarded helpers; repo contributors pass visibility.
- backend/app/api/exports.py: returns empty rows when analytics is not built.
- backend/app/services/analytics.py: repo analysis passes visibility to contributors.
- backend/app/main.py: `parse_target` validates DEFAULT_TARGETS (`repo:owner/name`, `user:`, `org:`); invalid entries are logged and skipped.

ELT
- data_pipeline/gitpulse_elt/github_client.py: `AuthRequiredError` for anonymous 401s; token-rejected message is distinct.
- data_pipeline/gitpulse_elt/extract.py: stargazer history is optional; a 401 records a warning and keeps the repository.

Frontend
- frontend/src/lib/api.ts: 25 s request timeout; network failure becomes a status-0 error with an actionable message.
- frontend/src/lib/auth.tsx: only 401/403 ends the session; transient failures expose `sessionError` and `retrySession`.
- frontend/src/App.tsx: session-error panel with retry; root `ErrorBoundary`.
- frontend/src/components/common/ErrorBoundary.tsx (new).
- frontend/src/lib/types.ts, frontend/src/pages/ContributorsPage.tsx: `basis` badge.
- frontend/src/__tests__/request_errors.test.ts (new).

Tests and docs
- tests/unit/test_regressions.py (new); .env.example; README.md; docs/WINDOWS_FIX_RUNBOOK.md (new).

## Commands
```powershell
# Database (PostgreSQL 17 running locally; the database is created once)
psql -U postgres -c "CREATE DATABASE gitpulse;"   # skip if it already exists

# Migrations (non-destructive; applies only pending revisions)
cd D:\Project\gitpulse\backend
..\.venv\Scripts\alembic.exe upgrade head

# Backend
cd D:\Project\gitpulse
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000

# Frontend (second PowerShell window)
cd D:\Project\gitpulse\frontend
npm ci
npm run dev        # http://localhost:5173 or http://<LAN-IP>:5173

# Initial sync (GitHub live). Set GITHUB_TOKEN in .env first for stargazers and higher limits.
cd D:\Project\gitpulse\data_pipeline
$env:PYTHONPATH="D:\Project\gitpulse\backend;D:\Project\gitpulse\data_pipeline;D:\Project\gitpulse"
python -m gitpulse_elt run --target repo:octocat/Hello-World
python -m gitpulse_elt run --target repo:pallets/click

# Labelled synthetic seed (demo only; flagged data_source=synthetic in the UI)
python -m gitpulse_elt run --mode synthetic_seed

# Tests
cd D:\Project\gitpulse
$env:GITPULSE_TEST_KEYS="<viewer>,<analyst>,<admin>"; $env:GITPULSE_DQ_LIVE="1"
python -m pytest tests -q
cd frontend; npx vitest run; npm run build
```

## Notes
- The `repo/click` form in DEFAULT_TARGETS names owner `repo`. Use `repo:pallets/click`.
- Without GITHUB_TOKEN, `/stargazers` returns 401 on GitHub. The repo still syncs and a warning is logged.
