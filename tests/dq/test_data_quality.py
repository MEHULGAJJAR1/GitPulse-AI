"""Data-quality tests: the check catalogue is well formed, and (when a database is reachable)
the checks run and persist results for the latest run without errors."""
import os

import pytest

from gitpulse_elt import quality  # noqa: E402


def test_every_check_has_a_valid_definition():
    checks = list(quality.CHECKS)
    assert checks, "quality module should define checks"
    names = [c.name for c in checks]
    assert len(names) == len(set(names)), "check names must be unique"
    for c in checks:
        assert c.severity in {"error", "warn"}, c.name
        assert c.model, c.name


def _db_available() -> bool:
    try:
        from app.config import get_settings
        from app.db import get_engine
        from sqlalchemy import text

        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return bool(get_settings().database_url)
    except Exception:
        return False


@pytest.mark.skipif(not _db_available() or not os.environ.get("GITPULSE_DQ_LIVE"), reason="set GITPULSE_DQ_LIVE=1 with a migrated database")
def test_checks_run_and_summarise_on_latest_run():
    from sqlalchemy import text

    from app.db import get_engine

    engine = get_engine()
    with engine.connect() as conn:
        run_id = conn.execute(text("SELECT max(id) FROM pipeline_runs")).scalar()
    summary = quality.run_checks(engine, run_id)
    assert set(summary) >= {"pass", "fail", "warn"}
    assert summary["fail"] == 0, "no error-severity check should fail on the latest run"
