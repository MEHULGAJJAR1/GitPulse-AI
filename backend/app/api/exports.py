"""CSV / JSON exports of stored data with column selection (custom reports)."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import text

from backend.app.config import get_settings
from backend.app.deps import Conn, Viewer
from backend.app.services import queries as q
from backend.app.services.analytics import health_input, portfolio_anomalies
from ml_analytics.health import score_repository

router = APIRouter(prefix="/exports")
MAX_ROWS = 20000

DATASETS = {
    "repos": ["repo_full_name", "owner", "language", "data_source", "stars", "forks", "open_issues", "prs_open",
              "commits_30d", "commits_window", "contributors_count", "median_merge_hours", "days_since_push"],
    "daily": ["repo_full_name", "activity_date", "commits", "issues_opened", "issues_closed", "prs_opened",
              "prs_merged", "releases", "stars_gained", "cumulative_stars_observed", "data_source"],
    "commits": ["repo_full_name", "sha", "author_login", "committed_at", "message_headline", "data_source"],
    "issues": ["repo_full_name", "number", "title", "state", "author_login", "created_at", "closed_at", "close_hours", "data_source"],
    "pulls": ["repo_full_name", "number", "title", "state", "author_login", "created_at", "merged_at", "merge_hours", "data_source"],
    "contributors": ["repo_full_name", "login", "commits_total", "commits_30d", "active_days", "share_of_commits", "rank_in_repo"],
    "health": ["repo_full_name", "health_score", "grade", "confidence", "weakest_component", "data_source"],
    "anomalies": ["repo_full_name", "date", "value", "expected", "z_score", "type", "severity", "explanation"],
}


def _rows(conn, dataset: str, days: int, repo: str | None, priv: bool) -> list[dict]:
    if not q.analytics_ready(conn):  # nothing built yet: export an empty, honestly-labelled file
        return []
    p = {"priv": priv, "days": days, "r": repo}
    if dataset == "repos":
        rows = q.repo_summaries(conn, priv=priv, days=days)
        out = []
        for r in rows:
            out.append({"repo_full_name": r["repo_full_name"], "owner": r["owner"], "language": r["language"],
                        "data_source": r["data_source"], "stars": r["stars"], "forks": r["forks"],
                        "open_issues": r["issues_open"], "prs_open": r["prs_open"], "commits_30d": r["commits_30d"],
                        "commits_window": r["commits_window"], "contributors_count": r["contributors_count"],
                        "median_merge_hours": r["median_merge_hours"], "days_since_push": r["days_since_push"]})
        return out
    if dataset == "health":
        return [{"repo_full_name": r["repo_full_name"], "health_score": (sc := score_repository(health_input(r)))["score"],
                 "grade": sc["grade"], "confidence": sc["confidence"], "weakest_component": sc["weakest_component"],
                 "data_source": r["data_source"]} for r in q.repo_summaries(conn, priv=priv, days=days)]
    if dataset == "anomalies":
        return portfolio_anomalies(conn, priv=priv, days=days, repo=repo).get("anomalies", [])
    sql = {
        "daily": """SELECT d.repo_full_name, d.activity_date::text AS activity_date, d.commits, d.issues_opened, d.issues_closed,
                    d.prs_opened, d.prs_merged, d.releases, d.stars_gained, d.cumulative_stars_observed, d.data_source
                    FROM analytics.mart_repo_daily d JOIN analytics.mart_repo_summary s ON s.repo_full_name = d.repo_full_name
                    WHERE (NOT s.is_private OR :priv) AND (CAST(:r AS TEXT) IS NULL OR d.repo_full_name = CAST(:r AS TEXT))
                    AND d.activity_date >= current_date - make_interval(days => CAST(:days AS INT)) ORDER BY 1, 2""",
        "commits": """SELECT c.repo_full_name, c.sha, c.author_login, c.committed_at, c.message_headline, c.data_source
                    FROM analytics.stg_commits c JOIN analytics.mart_repo_summary s ON s.repo_full_name = c.repo_full_name
                    WHERE (NOT s.is_private OR :priv) AND (CAST(:r AS TEXT) IS NULL OR c.repo_full_name = CAST(:r AS TEXT))
                    AND c.committed_at >= now() - make_interval(days => CAST(:days AS INT)) ORDER BY c.committed_at DESC""",
        "issues": """SELECT i.repo_full_name, i.number, i.title, i.state, i.author_login, i.created_at, i.closed_at,
                    r.close_hours, i.data_source FROM analytics.stg_issues i
                    JOIN analytics.mart_repo_summary s ON s.repo_full_name = i.repo_full_name
                    LEFT JOIN analytics.int_issue_resolution r ON r.repo_full_name = i.repo_full_name AND r.number = i.number
                    WHERE (NOT s.is_private OR :priv) AND (CAST(:r AS TEXT) IS NULL OR i.repo_full_name = CAST(:r AS TEXT))
                    AND i.created_at >= now() - make_interval(days => CAST(:days AS INT)) ORDER BY i.created_at DESC""",
        "pulls": """SELECT p.repo_full_name, p.number, p.title, p.state, p.author_login, p.created_at, p.merged_at,
                    c.merge_hours, p.data_source FROM analytics.stg_pull_requests p
                    JOIN analytics.mart_repo_summary s ON s.repo_full_name = p.repo_full_name
                    LEFT JOIN analytics.int_pr_cycle_times c ON c.repo_full_name = p.repo_full_name AND c.number = p.number
                    WHERE (NOT s.is_private OR :priv) AND (CAST(:r AS TEXT) IS NULL OR p.repo_full_name = CAST(:r AS TEXT))
                    AND p.created_at >= now() - make_interval(days => CAST(:days AS INT)) ORDER BY p.created_at DESC""",
        "contributors": """SELECT a.repo_full_name, a.login, a.commits_total, a.commits_30d, a.active_days,
                    a.share_of_commits, a.rank_in_repo FROM analytics.mart_contributor_activity a
                    JOIN analytics.mart_repo_summary s ON s.repo_full_name = a.repo_full_name
                    WHERE (NOT s.is_private OR :priv) AND (CAST(:r AS TEXT) IS NULL OR a.repo_full_name = CAST(:r AS TEXT))
                    ORDER BY a.repo_full_name, a.rank_in_repo""",
    }[dataset]
    return q.rows(conn, sql, **p)


def _jsonable(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        out.append({k: (v.isoformat() if hasattr(v, "isoformat") else (float(v) if type(v).__name__ == "Decimal" else v))
                    for k, v in r.items()})
    return out


@router.get("/{dataset}", tags=["exports"])
def export(principal: Viewer, conn: Conn,
           dataset: Literal["repos", "daily", "commits", "issues", "pulls", "contributors", "health", "anomalies"],
           format: Literal["csv", "json"] = "csv",
           days: int = Query(90, ge=1, le=730),
           repo: str | None = Query(None, pattern=r"^[A-Za-z0-9_.-]{1,39}/[A-Za-z0-9_.-]{1,100}$"),
           columns: str | None = Query(None, max_length=500, description="comma-separated subset of columns")):
    allowed = DATASETS[dataset]
    cols = allowed
    if columns:
        requested = [c.strip() for c in columns.split(",") if c.strip()]
        bad = [c for c in requested if c not in allowed]
        if bad:
            raise HTTPException(400, f"unknown columns for {dataset}: {', '.join(bad)}")
        cols = requested
    rows = _rows(conn, dataset, days, repo, principal.can_see_private)
    truncated = len(rows) > MAX_ROWS
    rows = [{c: r.get(c) for c in cols} for r in rows[:MAX_ROWS]]
    rows = _jsonable(rows)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"gitpulse_{dataset}_{stamp}.{format}"
    mode = q.data_mode(conn, principal.can_see_private)
    if format == "json":
        body = json.dumps({"meta": {"dataset": dataset, "generated_at": datetime.now(timezone.utc).isoformat(),
                                    "row_count": len(rows), "truncated": truncated, "data_mode": mode,
                                    "columns": cols, "window_days": days, "repo": repo,
                                    "source": "GitPulse (GitHub REST API + synthetic demo rows flagged data_source=synthetic)"},
                           "rows": rows}, indent=2, default=str)
        media = "application/json"
    else:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)
        body = buf.getvalue()
        media = "text/csv"
    return Response(content=body, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"',
                             "X-Row-Count": str(len(rows)), "X-Truncated": str(truncated).lower()})

