"""Read-side SQL over the analytics schema (marts/staging) and operational tables.

Visibility: every repository-scoped query takes `priv` (bool). Public viewers never see rows with
is_private = true; analysts see them only when ALLOW_PRIVATE_REPOS is enabled (see security.Principal).
All user-supplied values are bound parameters - never interpolated into SQL.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection


def rows(conn: Connection, sql: str, **params: Any) -> list[dict]:
    result = conn.execute(text(sql), params)
    return [dict(r._mapping) for r in result]


def scalar(conn: Connection, sql: str, **params: Any):
    return conn.execute(text(sql), params).scalar()


def analytics_ready(conn: Connection) -> bool:
    return bool(scalar(conn, "SELECT to_regclass('analytics.mart_repo_summary') IS NOT NULL"))


def data_mode(conn: Connection, priv: bool) -> dict:
    if not analytics_ready(conn):
        return {"mode": "empty", "github_repos": 0, "synthetic_repos": 0}
    counts = rows(conn, """
        SELECT data_source, count(*) AS n FROM analytics.stg_repositories
        WHERE (NOT is_private OR :priv) GROUP BY data_source
    """, priv=priv)
    by = {r["data_source"]: int(r["n"]) for r in counts}
    gh, syn = by.get("github", 0), by.get("synthetic", 0)
    mode = "empty" if gh + syn == 0 else "live" if syn == 0 else "synthetic" if gh == 0 else "mixed"
    return {"mode": mode, "github_repos": gh, "synthetic_repos": syn}


# ----------------------------------------------------------------- repositories
REPO_SUMMARY_SQL = """
WITH win AS (
    SELECT repo_full_name,
           sum(commits)          AS commits_window,
           sum(prs_merged)       AS prs_merged_window,
           sum(prs_opened)       AS prs_opened_window,
           sum(issues_closed)    AS issues_closed_window,
           sum(issues_opened)    AS issues_opened_window,
           sum(stars_gained)     AS stars_gained_window
    FROM analytics.mart_repo_daily
    WHERE activity_date >= current_date - make_interval(days => CAST(:days AS INT))
    GROUP BY 1
)
SELECT s.*,
       coalesce(w.commits_window, 0)        AS commits_window,
       coalesce(w.prs_merged_window, 0)     AS prs_merged_window,
       coalesce(w.prs_opened_window, 0)     AS prs_opened_window,
       coalesce(w.issues_closed_window, 0)  AS issues_closed_window,
       coalesce(w.issues_opened_window, 0)  AS issues_opened_window,
       coalesce(w.stars_gained_window, 0)   AS stars_gained_window
FROM analytics.mart_repo_summary s
LEFT JOIN win w ON w.repo_full_name = s.repo_full_name
WHERE (NOT s.is_private OR :priv)
  AND (CAST(:language AS TEXT) IS NULL OR s.language = CAST(:language AS TEXT))
  AND (CAST(:data_source AS TEXT) IS NULL OR s.data_source = CAST(:data_source AS TEXT))
  AND (CAST(:q AS TEXT) IS NULL OR s.repo_full_name ILIKE CAST(:q AS TEXT))
  AND (CAST(:owner AS TEXT) IS NULL OR s.owner = CAST(:owner AS TEXT))
"""


def repo_summaries(conn: Connection, *, priv: bool, days: int = 30, language=None, data_source=None,
                   q=None, owner=None) -> list[dict]:
    return rows(conn, REPO_SUMMARY_SQL, priv=priv, days=days, language=language, data_source=data_source,
                q=f"%{q}%" if q else None, owner=owner)


def repo_summary(conn: Connection, full_name: str, priv: bool, days: int = 30) -> dict | None:
    data = [r for r in repo_summaries(conn, priv=priv, days=days) if r["repo_full_name"] == full_name]
    return data[0] if data else None


def repo_languages(conn: Connection, full_name: str) -> list[dict]:
    return rows(conn, """
        SELECT language, bytes_of_code FROM analytics.stg_languages
        WHERE repo_full_name = :r ORDER BY bytes_of_code DESC
    """, r=full_name)


def repo_releases(conn: Connection, full_name: str, limit: int = 10) -> list[dict]:
    return rows(conn, """
        SELECT tag_name, release_name, published_at, is_prerelease FROM analytics.stg_releases
        WHERE repo_full_name = :r ORDER BY published_at DESC NULLS LAST LIMIT :lim
    """, r=full_name, lim=limit)


def repo_timeseries(conn: Connection, full_name: str, days: int) -> list[dict]:
    return rows(conn, """
        SELECT activity_date, commits, issues_opened, issues_closed, prs_opened, prs_merged, releases,
               stars_gained, cumulative_stars_observed
        FROM analytics.mart_repo_daily
        WHERE repo_full_name = :r AND activity_date >= current_date - make_interval(days => CAST(:days AS INT))
        ORDER BY activity_date
    """, r=full_name, days=days)


def heatmap(conn: Connection, *, full_name: str | None, priv: bool) -> list[dict]:
    return rows(conn, """
        SELECT h.weekday, h.hour_utc, sum(h.commits) AS commits
        FROM analytics.mart_commit_heatmap h
        JOIN analytics.mart_repo_summary s ON s.repo_full_name = h.repo_full_name
        WHERE (NOT s.is_private OR :priv)
          AND (CAST(:r AS TEXT) IS NULL OR h.repo_full_name = CAST(:r AS TEXT))
        GROUP BY 1, 2 ORDER BY 1, 2
    """, priv=priv, r=full_name)


def daily_heatmap(conn: Connection, *, priv: bool, days: int, full_name: str | None = None) -> list[dict]:
    return rows(conn, """
        SELECT d.activity_date::text AS date, sum(d.commits) AS commits
        FROM analytics.mart_repo_daily d
        JOIN analytics.mart_repo_summary s ON s.repo_full_name = d.repo_full_name
        WHERE (NOT s.is_private OR :priv)
          AND (CAST(:r AS TEXT) IS NULL OR d.repo_full_name = CAST(:r AS TEXT))
          AND d.activity_date >= current_date - make_interval(days => CAST(:days AS INT))
        GROUP BY 1 ORDER BY 1
    """, priv=priv, r=full_name, days=days)


def overview_timeline(conn: Connection, *, priv: bool, days: int, language=None, data_source=None) -> list[dict]:
    return rows(conn, """
        SELECT d.activity_date::text AS date,
               sum(d.commits) AS commits, sum(d.issues_opened) AS issues_opened,
               sum(d.issues_closed) AS issues_closed, sum(d.prs_opened) AS prs_opened,
               sum(d.prs_merged) AS prs_merged, sum(d.stars_gained) AS stars_gained
        FROM analytics.mart_repo_daily d
        JOIN analytics.mart_repo_summary s ON s.repo_full_name = d.repo_full_name
        WHERE (NOT s.is_private OR :priv)
          AND (CAST(:language AS TEXT) IS NULL OR s.language = CAST(:language AS TEXT))
          AND (CAST(:ds AS TEXT) IS NULL OR s.data_source = CAST(:ds AS TEXT))
          AND d.activity_date >= current_date - make_interval(days => CAST(:days AS INT))
        GROUP BY 1 ORDER BY 1
    """, priv=priv, days=days, language=language, ds=data_source)


def language_distribution(conn: Connection, *, priv: bool) -> list[dict]:
    return rows(conn, """
        SELECT l.language, count(DISTINCT l.repo_full_name) AS repos, sum(l.bytes_of_code) AS bytes_total
        FROM analytics.stg_languages l
        JOIN analytics.mart_repo_summary s ON s.repo_full_name = l.repo_full_name
        WHERE (NOT s.is_private OR :priv)
        GROUP BY 1 ORDER BY bytes_total DESC
    """, priv=priv)


def contributor_ranking(conn: Connection, *, priv: bool, repo: str | None = None, limit: int = 50) -> list[dict]:
    return rows(conn, """
        SELECT a.login, count(DISTINCT a.repo_full_name) AS repos, sum(a.commits_total) AS commits_total,
               sum(a.commits_30d) AS commits_30d, sum(a.active_days) AS active_days,
               max(a.last_commit_at) AS last_commit_at
        FROM analytics.mart_contributor_activity a
        JOIN analytics.mart_repo_summary s ON s.repo_full_name = a.repo_full_name
        WHERE (NOT s.is_private OR :priv)
          AND (CAST(:r AS TEXT) IS NULL OR a.repo_full_name = CAST(:r AS TEXT))
        GROUP BY a.login ORDER BY commits_total DESC LIMIT :lim
    """, priv=priv, r=repo, lim=limit)


def repo_contributors(conn: Connection, full_name: str) -> list[dict]:
    return rows(conn, """
        SELECT login, commits_total, commits_30d, active_days, share_of_commits, rank_in_repo,
               first_commit_at, last_commit_at
        FROM analytics.mart_contributor_activity WHERE repo_full_name = :r
        ORDER BY commits_total DESC
    """, r=full_name)


def contributor_activity(conn: Connection, login: str, priv: bool) -> dict:
    repos = rows(conn, """
        SELECT a.repo_full_name, a.commits_total, a.commits_30d, a.active_days, a.share_of_commits
        FROM analytics.mart_contributor_activity a
        JOIN analytics.mart_repo_summary s ON s.repo_full_name = a.repo_full_name
        WHERE a.login = :l AND (NOT s.is_private OR :priv) ORDER BY a.commits_total DESC
    """, l=login, priv=priv)
    daily = rows(conn, """
        SELECT committed_at::date::text AS date, count(*) AS commits
        FROM analytics.stg_commits c
        JOIN analytics.mart_repo_summary s ON s.repo_full_name = c.repo_full_name
        WHERE c.author_login = :l AND (NOT s.is_private OR :priv)
          AND committed_at >= now() - interval '365 days'
        GROUP BY 1 ORDER BY 1
    """, l=login, priv=priv)
    return {"repos": repos, "daily": daily}


def commits_page(conn: Connection, full_name: str, *, days: int, limit: int, offset: int) -> tuple[list[dict], int]:
    total = scalar(conn, """
        SELECT count(*) FROM analytics.stg_commits WHERE repo_full_name = :r
          AND committed_at >= now() - make_interval(days => CAST(:days AS INT))
    """, r=full_name, days=days)
    data = rows(conn, """
        SELECT sha, author_login, author_name, committed_at, message_headline, data_source
        FROM analytics.stg_commits WHERE repo_full_name = :r
          AND committed_at >= now() - make_interval(days => CAST(:days AS INT))
        ORDER BY committed_at DESC NULLS LAST LIMIT :lim OFFSET :off
    """, r=full_name, days=days, lim=limit, off=offset)
    return data, int(total or 0)


def issues_page(conn: Connection, full_name: str, *, state: str, limit: int, offset: int) -> tuple[list[dict], int]:
    cond = "" if state == "all" else "AND i.state = CAST(:state AS TEXT)"
    total = scalar(conn, f"SELECT count(*) FROM analytics.stg_issues i WHERE i.repo_full_name = :r {cond}",
                   r=full_name, state=state)
    data = rows(conn, f"""
        SELECT i.number, i.title, i.state, i.author_login, i.created_at, i.closed_at, i.comments, i.labels,
               r.close_hours, r.open_age_days
        FROM analytics.stg_issues i
        LEFT JOIN analytics.int_issue_resolution r ON r.repo_full_name = i.repo_full_name AND r.number = i.number
        WHERE i.repo_full_name = :r {cond}
        ORDER BY i.created_at DESC LIMIT :lim OFFSET :off
    """, r=full_name, state=state, lim=limit, off=offset)
    return data, int(total or 0)


def pulls_page(conn: Connection, full_name: str, *, state: str, limit: int, offset: int) -> tuple[list[dict], int]:
    cond = "" if state == "all" else "AND p.state = CAST(:state AS TEXT)"
    total = scalar(conn, f"SELECT count(*) FROM analytics.stg_pull_requests p WHERE p.repo_full_name = :r {cond}",
                   r=full_name, state=state)
    data = rows(conn, f"""
        SELECT p.number, p.title, p.state, p.author_login, p.created_at, p.merged_at, p.closed_at, p.is_draft,
               p.base_ref, p.head_ref, c.merge_hours
        FROM analytics.stg_pull_requests p
        LEFT JOIN analytics.int_pr_cycle_times c ON c.repo_full_name = p.repo_full_name AND c.number = p.number
        WHERE p.repo_full_name = :r {cond}
        ORDER BY p.created_at DESC LIMIT :lim OFFSET :off
    """, r=full_name, state=state, lim=limit, off=offset)
    return data, int(total or 0)


def pr_cycle(conn: Connection, *, priv: bool, days: int, repo: str | None) -> dict:
    weekly = rows(conn, """
        SELECT w.week_start::text AS week, sum(w.merged_prs) AS merged_prs,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY w.median_merge_hours) AS median_merge_hours,
               max(w.p90_merge_hours) AS p90_merge_hours
        FROM analytics.mart_pr_cycle_weekly w
        JOIN analytics.mart_repo_summary s ON s.repo_full_name = w.repo_full_name
        WHERE (NOT s.is_private OR :priv) AND (CAST(:r AS TEXT) IS NULL OR w.repo_full_name = CAST(:r AS TEXT))
          AND w.week_start >= current_date - make_interval(days => CAST(:days AS INT))
        GROUP BY 1 ORDER BY 1
    """, priv=priv, r=repo, days=days)
    dist = rows(conn, """
        SELECT c.merge_hours FROM analytics.int_pr_cycle_times c
        JOIN analytics.mart_repo_summary s ON s.repo_full_name = c.repo_full_name
        WHERE (NOT s.is_private OR :priv) AND (CAST(:r AS TEXT) IS NULL OR c.repo_full_name = CAST(:r AS TEXT))
          AND c.merged_at >= now() - make_interval(days => CAST(:days AS INT))
    """, priv=priv, r=repo, days=days)
    return {"weekly": weekly, "merge_hours": [float(r["merge_hours"]) for r in dist]}


def issue_aging(conn: Connection, *, priv: bool, repo: str | None) -> dict:
    buckets = rows(conn, """
        SELECT a.age_bucket, a.bucket_order, sum(a.open_issues) AS open_issues
        FROM analytics.mart_issue_aging a
        JOIN analytics.mart_repo_summary s ON s.repo_full_name = a.repo_full_name
        WHERE (NOT s.is_private OR :priv) AND (CAST(:r AS TEXT) IS NULL OR a.repo_full_name = CAST(:r AS TEXT))
        GROUP BY 1, 2 ORDER BY 2
    """, priv=priv, r=repo)
    resolution = rows(conn, """
        SELECT r.close_hours, r.state, r.open_age_days FROM analytics.int_issue_resolution r
        JOIN analytics.mart_repo_summary s ON s.repo_full_name = r.repo_full_name
        WHERE (NOT s.is_private OR :priv) AND (CAST(:r AS TEXT) IS NULL OR r.repo_full_name = CAST(:r AS TEXT))
    """, priv=priv, r=repo)
    return {"buckets": buckets, "resolution": resolution}


def search(conn: Connection, *, priv: bool, q: str, limit: int = 6) -> dict:
    like = f"%{q}%"
    repos = rows(conn, """
        SELECT repo_full_name, language, stars, data_source FROM analytics.mart_repo_summary
        WHERE (NOT is_private OR :priv) AND repo_full_name ILIKE :q ORDER BY stars DESC NULLS LAST LIMIT :lim
    """, priv=priv, q=like, lim=limit)
    contributors = rows(conn, """
        SELECT a.login, count(DISTINCT a.repo_full_name) AS repos, sum(a.commits_total) AS commits_total
        FROM analytics.mart_contributor_activity a
        JOIN analytics.mart_repo_summary s ON s.repo_full_name = a.repo_full_name
        WHERE (NOT s.is_private OR :priv) AND a.login ILIKE :q GROUP BY a.login ORDER BY commits_total DESC LIMIT :lim
    """, priv=priv, q=like, lim=limit)
    issues = rows(conn, """
        SELECT i.repo_full_name, i.number, i.title, i.state FROM analytics.stg_issues i
        JOIN analytics.mart_repo_summary s ON s.repo_full_name = i.repo_full_name
        WHERE (NOT s.is_private OR :priv) AND i.title ILIKE :q ORDER BY i.created_at DESC LIMIT :lim
    """, priv=priv, q=like, lim=limit)
    return {"repos": repos, "contributors": contributors, "issues": issues}


def recent_runs(conn: Connection, limit: int = 20) -> list[dict]:
    return rows(conn, """
        SELECT id, trigger, status, stage, targets, stats, error, requested_by, created_at, started_at, finished_at
        FROM pipeline_runs ORDER BY id DESC LIMIT :lim
    """, lim=limit)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
