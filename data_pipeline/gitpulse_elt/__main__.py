"""Command-line entry point used by scripts, cron and the Airflow DAG.

Examples:
  python -m gitpulse_elt run --target repo:octocat/Hello-World
  python -m gitpulse_elt run                      # uses enabled tracked targets
  python -m gitpulse_elt run --mode synthetic_seed  # labelled demo fallback
  python -m gitpulse_elt transform                # rebuild analytics models only
  python -m gitpulse_elt quality                  # run data-quality checks only
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))


def _bootstrap():
    from app.config import get_settings
    from app.db import get_engine
    from app.logging_setup import configure_logging, register_secret

    settings = get_settings()
    configure_logging(settings.log_level)
    for s in (settings.github_token, settings.llm_api_key):
        register_secret(s)
    return settings, get_engine()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gitpulse_elt")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run_p = sub.add_parser("run", help="run the full ELT pipeline")
    run_p.add_argument("--target", action="append", default=None, help="kind:owner/name (repeatable)")
    run_p.add_argument("--mode", default="github", choices=["github", "synthetic_seed", "synthetic_clear"])
    run_p.add_argument("--trigger", default="cli")
    sub.add_parser("transform", help="rebuild staging/intermediate/mart models")
    sub.add_parser("quality", help="run data-quality checks on the current analytics tables")
    args = parser.parse_args(argv)

    settings, engine = _bootstrap()
    from gitpulse_elt.runner import run_pipeline
    from gitpulse_elt.transform import run_transforms
    from gitpulse_elt.quality import run_checks
    from gitpulse_elt.runner import RunLogger, create_run

    if args.cmd == "run":
        result = asyncio.run(run_pipeline(engine, settings, trigger=args.trigger, targets=args.target, mode=args.mode))
        print(json.dumps({k: v for k, v in result.items() if k != "stats"}, default=str))
        return 0 if result["status"] in ("succeeded", "partial") else 1
    if args.cmd == "transform":
        for name, rows in run_transforms(engine, Path(settings.dbt_models_dir)):
            print(f"{name}: {rows}")
        return 0
    if args.cmd == "quality":
        run_id = create_run(engine, "cli", "cli", None, "quality")
        summary = run_checks(engine, run_id, RunLogger(engine, run_id))
        print(json.dumps(summary))
        return 0 if summary["fail"] == 0 else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
