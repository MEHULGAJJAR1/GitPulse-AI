#!/usr/bin/env bash
# Start a GitPulse service in the foreground.  Usage: ./scripts/run.sh api|web|pipeline
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source .venv/bin/activate
case "${1:-}" in
  api)      cd backend && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload ;;
  web)      cd frontend && exec npm run dev ;;
  pipeline) cd data_pipeline && exec python -m gitpulse_elt run ;;
  *) echo "usage: $0 api|web|pipeline" >&2; exit 2 ;;
esac
