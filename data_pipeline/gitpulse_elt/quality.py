"""Data-quality checks executed after the transform stage.

Each check counts violating rows. `error` severity failing checks fail the run; `warn`
checks are recorded but do not fail it. The same invariants are also declared as dbt tests
in dbt/models/schema.yml for teams that run dbt directly.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine, text


@dataclass(frozen=True)
class Check:
    name: str
    model: str
    severity: str  # error | warn
    sql: str  # must return a single integer: number of failing rows
    description: str


CHECKS: tuple[Check, ...] = (
    Check("unique_repo_full_name", "stg_repositories", "error",
          "SELECT count(*) - count(DISTINCT full_name) FROM analytics.stg_repositories",
          "Repository full_name is unique in staging"),
    Check("not_null_repo_full_name", "stg_repositories", "error",
          "SELECT count(*) FROM analytics.stg_repositories WHERE full_name IS NULL",
          "Repository full_name is never null"),
    Check("unique_commit_per_repo", "stg_commits", "error",
          "SELECT count(*) FROM (SELECT repo_full_name, sha FROM analytics.stg_commits GROUP BY 1,2 HAVING count(*) > 1) d",
          "Commit SHA is unique within a repository"),
    Check("commit_timestamps_not_future", "stg_commits", "error",
          "SELECT count(*) FROM analytics.stg_commits WHERE committed_at > now() + interval '1 day'",
          "Commit timestamps are not in the future"),
    Check("issue_state_domain", "stg_issues", "error",
          "SELECT count(*) FROM analytics.stg_issues WHERE state NOT IN ('open','closed')",
          "Issue state is open or closed"),
    Check("merged_implies_closed", "stg_pull_requests", "error",
          "SELECT count(*) FROM analytics.stg_pull_requests WHERE merged_at IS NOT NULL AND state <> 'closed'",
          "A merged pull request is closed"),
    Check("merge_after_create", "int_pr_cycle_times", "error",
          "SELECT count(*) FROM analytics.int_pr_cycle_times WHERE merge_hours < 0",
          "Merge time is never negative"),
    Check("commits_reference_known_repo", "stg_commits", "warn",
          "SELECT count(*) FROM analytics.stg_commits c LEFT JOIN analytics.stg_repositories r "
          "ON r.full_name = c.repo_full_name WHERE r.full_name IS NULL",
          "Every commit belongs to a staged repository (referential integrity)"),
    Check("daily_mart_unique_grain", "mart_repo_daily", "error",
          "SELECT count(*) - count(DISTINCT (repo_full_name, activity_date)) FROM analytics.mart_repo_daily",
          "mart_repo_daily has one row per repository and day"),
    Check("non_negative_activity", "mart_repo_daily", "error",
          "SELECT count(*) FROM analytics.mart_repo_daily WHERE commits < 0 OR issues_opened < 0 OR prs_merged < 0",
          "Activity counts are non-negative"),
    Check("health_score_range", "mart_repo_summary", "error",
          "SELECT count(*) FROM analytics.mart_repo_summary WHERE stars < 0 OR forks < 0",
          "Repository counters are non-negative"),
    Check("repos_present", "stg_repositories", "warn",
          "SELECT CASE WHEN count(*) = 0 THEN 1 ELSE 0 END FROM analytics.stg_repositories",
          "At least one repository is staged"),
    Check("raw_recent_ingestion", "raw.github_payloads", "warn",
          "SELECT CASE WHEN max(last_seen_at) < now() - interval '7 days' THEN 1 ELSE 0 END FROM raw.github_payloads",
          "Raw layer received data within the last 7 days"),
)


def run_checks(engine: Engine, run_id: int, emit=None) -> dict[str, int]:
    """Run all checks, persist results, return {'pass': n, 'fail': n, 'warn': n}."""
    summary = {"pass": 0, "fail": 0, "warn": 0}
    for check in CHECKS:
        try:
            with engine.connect() as conn:
                failing = int(conn.execute(text(check.sql)).scalar_one() or 0)
            detail = check.description
            if failing == 0:
                status = "pass"
            else:
                status = "fail" if check.severity == "error" else "warn"
                detail = f"{check.description}: {failing} failing row(s)"
        except Exception as exc:  # noqa: BLE001 - a broken check is itself a failure
            failing, status = 1, "fail"
            detail = f"check could not run: {type(exc).__name__}: {str(exc)[:200]}"
        summary["fail" if status == "fail" else ("warn" if status == "warn" else "pass")] += 1
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO data_quality_results (run_id, check_name, model, severity, status, failing_rows, detail) "
                    "VALUES (:r, :c, :m, :s, :st, :f, :d)"
                ),
                {"r": run_id, "c": check.name, "m": check.model, "s": check.severity, "st": status, "f": failing, "d": detail},
            )
        if emit:
            emit("ERROR" if status == "fail" else ("WARNING" if status == "warn" else "INFO"), "quality",
                 f"{check.name}: {status} ({detail})")
    return summary
