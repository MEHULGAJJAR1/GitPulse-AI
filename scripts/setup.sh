#!/usr/bin/env bash
# GitPulse setup for macOS / Linux.
# Usage:  ./scripts/setup.sh [--seed-demo] [--skip-frontend] [--run-tests]
# Requires: Python 3.13 (3.11+ works), Node.js 20+ and npm, PostgreSQL 14+ reachable at DATABASE_URL.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
SEED_DEMO=0; SKIP_FRONTEND=0; RUN_TESTS=0
for arg in "$@"; do
  case "$arg" in
    --seed-demo) SEED_DEMO=1 ;;
    --skip-frontend) SKIP_FRONTEND=1 ;;
    --run-tests) RUN_TESTS=1 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

log() { printf '\033[1;36m==> %s\033[0m\n' "$*"; }

PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null || { echo "python3 not found"; exit 1; }
"$PY" -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ required"'

log "Creating virtualenv at .venv"
[ -d .venv ] || "$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null
log "Installing Python dependencies (backend, ELT, ML, tests)"
pip install -r requirements-dev.txt

if [ ! -f .env ]; then
  log "Creating .env with freshly generated API keys"
  python - <<'PY'
import secrets, pathlib
tpl = pathlib.Path(".env.example").read_text()
for name in ["API_KEYS_VIEWER", "API_KEYS_ANALYST", "API_KEYS_ADMIN"]:
    tpl = tpl.replace(f"{name}=change-me-{name.split('_')[-1].lower()}-key", f"{name}={secrets.token_urlsafe(24)}")
tpl = tpl.replace("POSTGRES_PASSWORD=change-me-postgres", f"POSTGRES_PASSWORD={secrets.token_urlsafe(16)}")
pathlib.Path(".env").write_text(tpl)
PY
  echo "Keys were written to .env (keep it private). Add GITHUB_TOKEN to .env for higher GitHub rate limits."
else
  log ".env already exists; leaving it unchanged"
fi

log "Applying database migrations (alembic)"
(cd backend && alembic upgrade head)

if [ "$SEED_DEMO" = "1" ]; then
  log "Seeding LABELLED SYNTHETIC demo data (not GitHub data)"
  (cd data_pipeline && python -m gitpulse_elt run --mode synthetic_seed)
fi

if [ "$SKIP_FRONTEND" = "0" ]; then
  log "Installing and building the frontend"
  (cd frontend && npm ci && npm run build)
fi

if [ "$RUN_TESTS" = "1" ]; then
  "$ROOT/scripts/test.sh"
fi

cat <<'EOF'

Setup complete.
  Start API:       ./scripts/run.sh api
  Start web app:   ./scripts/run.sh web      (http://localhost:5173)
  Sign in with the API_KEYS_ADMIN value from .env
EOF
