#!/usr/bin/env bash
# Runs every test layer. Live API/DQ tests run only when the server/database is reachable.
# Usage: ./scripts/test.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source .venv/bin/activate

echo "== Python: unit, ML evaluation, data quality, API"
if [ -f .env ]; then
  KEYS="$(python - <<'PY'
env = dict(l.split("=", 1) for l in open(".env") if "=" in l and not l.startswith("#"))
pick = lambda k: env.get(k, "").split(",")[0].split(":")[-1].strip()
print(",".join([pick("API_KEYS_VIEWER"), pick("API_KEYS_ANALYST"), pick("API_KEYS_ADMIN")]))
PY
)"
  export GITPULSE_TEST_KEYS="$KEYS"
fi
export GITPULSE_DQ_LIVE="${GITPULSE_DQ_LIVE:-1}"
python -m pytest tests -q

echo "== Frontend: type check, unit/component tests, production build"
(cd frontend && npm run build && npx vitest run)

echo "== dbt (optional, needs dbt-core and profiles.yml)"
if command -v dbt >/dev/null && [ -f "$HOME/.dbt/profiles.yml" ]; then
  (cd dbt && dbt parse)
else
  echo "skipped: dbt not configured"
fi
echo "All selected test layers passed."
