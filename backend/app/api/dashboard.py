"""Dashboard KPIs, repository explorer, drill-downs, search, notifications and org comparison."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Literal

import pandas as pd
from fastapi import APIRouter, HTTPException, Path, Query
from sqlalchemy import text

from backend.app.deps import Conn, NamePath, OwnerPath, Viewer, full_name
from backend.app.services import queries as q
from backend.app.services.analytics import daily_frame, health_input, portfolio_anomalies, portfolio_health
from ml_analytics.health import score_repository

router = APIRouter()
Days = Query(30, ge=1, le=730)
DataSource = Query(None, pattern="^(github|synthetic)$")


def _median(values):
    vals = [float(v) for v in values if v is not None]
    return round(float(pd.Series(vals).median()), 2) if vals else None


@router.get("/dashboard/overview", tags=["dashboard"])
def overview(principal: Viewer, conn: Conn, days: int = Days, language: str | None = None,
             data_source: str | None = DataSource):
    priv = principal.can_see_private
    mode = q.data_mode(conn, priv)
    summaries = q.repo_summaries(conn, priv=priv, days=days, language=language, data_source=data_source)
    timeline = q.overview_timeline(conn, priv=priv, days=days, language=language, data_source=data_source)
    prev_commits = q.previous_window_commits(conn, priv=priv, days=days)
    commits_now = sum(int(s["commits_window"] or 0) for s in summaries)
    scores = [score_repository(health_input(s)) for s in summaries]
    grades = Counter(s["grade"] for s in scores)
    languages = q.language_distribution(conn, priv=priv)
    total_bytes = sum(int(l["bytes_total"] or 0) for l in languages) or 1
    contributors_total = q.visible_contributor_count(conn, priv=priv)
    leaderboard = sorted(summaries, key=lambda s: (-(s["commits_window"] or 0), -(s["stars"] or 0)))[:10]
    leader_out = []
    for s in leaderboard:
        sc = next(x for x in scores if x["repo_full_name"] == s["repo_full_name"])
        leader_out.append({
            "repo_full_name": s["repo_full_name"], "language": s["language"], "stars": s["stars"],
            "commits_window": s["commits_window"], "prs_merged_window": s["prs_merged_window"],
            "issues_closed_window": s["issues_closed_window"], "health_score": sc["score"], "grade": sc["grade"],
            "data_source": s["data_source"],
        })
    anomalies = portfolio_anomalies(conn, priv=priv, days=max(days, 60))
    recent_anoms = [a for a in anomalies.get("anomalies", []) if a["date"] >= (datetime.now(timezone.utc).date() - pd.Timedelta(days=14).to_pytimedelta()).isoformat()]
    return {
        "data_mode": mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window": {"days": days, "end": datetime.now(timezone.utc).date().isoformat()},
        "filters": {"language": language, "data_source": data_source},
        "kpis": {
            "repositories": len(summaries),
            "stars_total": sum(int(s["stars"] or 0) for s in summaries),
            "stars_gained_window": sum(int(s["stars_gained_window"] or 0) for s in summaries),
            "commits_window": commits_now,
            "commits_previous_window": prev_commits,
            "commit_change_pct": round((commits_now - prev_commits) / prev_commits * 100, 1) if prev_commits else None,
            "open_issues": sum(int(s["issues_open"] or 0) for s in summaries),
            "open_prs": sum(int(s["prs_open"] or 0) for s in summaries),
            "prs_merged_window": sum(int(s["prs_merged_window"] or 0) for s in summaries),
            "issues_closed_window": sum(int(s["issues_closed_window"] or 0) for s in summaries),
            "median_merge_hours": _median([s["median_merge_hours"] for s in summaries]),
            "median_issue_close_hours": _median([s["median_issue_close_hours"] for s in summaries]),
            "avg_health_score": round(sum(s["score"] for s in scores) / len(scores), 1) if scores else None,
            "contributors_total": contributors_total,
            "anomalies_last_14_days": len(recent_anoms),
        },
        "timeline": timeline,
        "languages": [{**l, "share": round((l["bytes_total"] or 0) / total_bytes, 4)} for l in languages],
        "leaderboard": leader_out,
        "health_distribution": {g: grades.get(g, 0) for g in "ABCDE"},
        "recent_anomalies": recent_anoms[:8],
    }


@router.get("/repos", tags=["repositories"])
def list_repos(
    principal: Viewer, conn: Conn,
    q_text: str | None = Query(None, alias="q", max_length=100),
    language: str | None = Query(None, max_length=60),
    data_source: str | None = DataSource,
    owner: str | None = Query(None, pattern=r"^[A-Za-z0-9_.-]{1,39}$"),
    sort: Literal["stars", "commits", "health", "name", "issues", "merge_time"] = "stars",
    order: Literal["asc", "desc"] = "desc",
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(25, ge=1, le=100),
    days: int = Days,
):
    summaries = q.repo_summaries(conn, priv=principal.can_see_private, days=days, language=language,
                                 data_source=data_source, q=q_text, owner=owner)
    items = []
    for s in summaries:
        sc = score_repository(health_input(s))
        items.append({
            "repo_full_name": s["repo_full_name"], "owner": s["owner"], "name": s["name"], "language": s["language"],
            "stars": s["stars"], "forks": s["forks"], "open_issues": s["issues_open"], "prs_open": s["prs_open"],
            "commits_window": s["commits_window"], "commits_30d": s["commits_30d"], "contributors": s["contributors_count"],
            "median_merge_hours": s["median_merge_hours"], "days_since_push": s["days_since_push"],
            "health_score": sc["score"], "grade": sc["grade"], "data_source": s["data_source"],
            "is_private": s["is_private"], "pushed_at": s["pushed_at"],
        })
    keymap = {
        "stars": lambda x: x["stars"] or 0, "commits": lambda x: x["commits_window"] or 0,
        "health": lambda x: x["health_score"], "name": lambda x: x["repo_full_name"].lower(),
        "issues": lambda x: x["open_issues"] or 0, "merge_time": lambda x: x["median_merge_hours"] or 0,
    }
    items.sort(key=keymap[sort], reverse=(order == "desc"))
    total = len(items)
    start = (page - 1) * page_size
    return {"total": total, "page": page, "page_size": page_size,
            "pages": max(1, (total + page_size - 1) // page_size), "items": items[start:start + page_size]}


@router.get("/repos/{owner}/{name}", tags=["repositories"])
def repo_detail(principal: Viewer, conn: Conn, owner: OwnerPath, name: NamePath, days: int = Days):
    fn = full_name(owner, name)
    s = q.repo_summary(conn, fn, principal.can_see_private, days=days)
    if not s:
        raise HTTPException(404, "repository not found or not visible to your role")
    sc = score_repository(health_input(s))
    langs = q.repo_languages(conn, fn)
    total = sum(int(l["bytes_of_code"] or 0) for l in langs) or 1
    return {
        "summary": s,
        "health": sc,
        "languages": [{"language": l["language"], "bytes_of_code": l["bytes_of_code"],
                       "share": round(l["bytes_of_code"] / total, 4)} for l in langs],
        "releases": q.repo_releases(conn, fn),
        "data_source": s["data_source"],
        "is_synthetic": s["data_source"] == "synthetic",
    }


@router.get("/repos/{owner}/{name}/commits", tags=["repositories"])
def repo_commits(principal: Viewer, conn: Conn, owner: OwnerPath, name: NamePath,
                 days: int = Query(365, ge=1, le=3650), page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)):
    fn = full_name(owner, name)
    _ensure_visible(conn, fn, principal)
    items, total = q.commits_page(conn, fn, days=days, limit=page_size, offset=(page - 1) * page_size)
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/repos/{owner}/{name}/issues", tags=["repositories"])
def repo_issues(principal: Viewer, conn: Conn, owner: OwnerPath, name: NamePath,
                state: Literal["open", "closed", "all"] = "all", page: int = Query(1, ge=1),
                page_size: int = Query(25, ge=1, le=100)):
    fn = full_name(owner, name)
    _ensure_visible(conn, fn, principal)
    items, total = q.issues_page(conn, fn, state=state, limit=page_size, offset=(page - 1) * page_size)
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/repos/{owner}/{name}/pulls", tags=["repositories"])
def repo_pulls(principal: Viewer, conn: Conn, owner: OwnerPath, name: NamePath,
               state: Literal["open", "closed", "all"] = "all", page: int = Query(1, ge=1),
               page_size: int = Query(25, ge=1, le=100)):
    fn = full_name(owner, name)
    _ensure_visible(conn, fn, principal)
    items, total = q.pulls_page(conn, fn, state=state, limit=page_size, offset=(page - 1) * page_size)
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/repos/{owner}/{name}/timeseries", tags=["repositories"])
def repo_timeseries(principal: Viewer, conn: Conn, owner: OwnerPath, name: NamePath, days: int = Query(90, ge=7, le=730)):
    fn = full_name(owner, name)
    _ensure_visible(conn, fn, principal)
    rows = q.repo_timeseries(conn, fn, days)
    for r in rows:
        r["activity_date"] = r["activity_date"].isoformat()
    return {"repo_full_name": fn, "days": days, "items": rows}


@router.get("/repos/{owner}/{name}/contributors", tags=["repositories"])
def repo_contributors(principal: Viewer, conn: Conn, owner: OwnerPath, name: NamePath):
    fn = full_name(owner, name)
    _ensure_visible(conn, fn, principal)
    rows = q.repo_contributors(conn, fn, principal.can_see_private)
    for r in rows:
        for k in ("first_commit_at", "last_commit_at"):
            if r.get(k) is not None:
                r[k] = r[k].isoformat()
    return {"repo_full_name": fn, "items": rows}


@router.get("/repos/{owner}/{name}/heatmap", tags=["repositories"])
def repo_heatmap(principal: Viewer, conn: Conn, owner: OwnerPath, name: NamePath, days: int = Query(365, ge=7, le=730)):
    fn = full_name(owner, name)
    _ensure_visible(conn, fn, principal)
    return {"repo_full_name": fn, "weekday_hour": q.heatmap(conn, full_name=fn, priv=principal.can_see_private),
            "daily": q.daily_heatmap(conn, priv=principal.can_see_private, days=days, full_name=fn)}


@router.get("/heatmap", tags=["dashboard"])
def portfolio_heatmap(principal: Viewer, conn: Conn, days: int = Query(365, ge=7, le=730)):
    return {"weekday_hour": q.heatmap(conn, full_name=None, priv=principal.can_see_private),
            "daily": q.daily_heatmap(conn, priv=principal.can_see_private, days=days)}


@router.get("/contributors", tags=["contributors"])
def contributors(principal: Viewer, conn: Conn, repo: str | None = Query(None, pattern=r"^[A-Za-z0-9_.-]{1,39}/[A-Za-z0-9_.-]{1,100}$"),
                 limit: int = Query(50, ge=1, le=200)):
    rows = q.contributor_ranking(conn, priv=principal.can_see_private, repo=repo, limit=limit)
    for i, r in enumerate(rows, start=1):
        r["rank"] = i
        r["last_commit_at"] = r["last_commit_at"].isoformat() if r.get("last_commit_at") else None
    return {"items": rows, "repo": repo}


@router.get("/contributors/{login}", tags=["contributors"])
def contributor_detail(principal: Viewer, conn: Conn, login: str = Path(..., pattern=r"^[A-Za-z0-9-]{1,39}$")):
    data = q.contributor_activity(conn, login, principal.can_see_private)
    if not data["repos"]:
        raise HTTPException(404, "contributor not found in visible repositories")
    return {"login": login, **data}


@router.get("/search", tags=["search"])
def search(principal: Viewer, conn: Conn, q_text: str = Query(..., alias="q", min_length=2, max_length=100)):
    return {"query": q_text, **q.search(conn, priv=principal.can_see_private, q=q_text)}


@router.get("/owners/compare", tags=["dashboard"])
def compare_owners(principal: Viewer, conn: Conn, days: int = Days):
    """Organisation / owner comparison: aggregates per owner (org or user)."""
    summaries = q.repo_summaries(conn, priv=principal.can_see_private, days=days)
    groups: dict[str, list[dict]] = {}
    for s in summaries:
        groups.setdefault(s["owner"] or "unknown", []).append(s)
    out = []
    for owner, items in groups.items():
        scores = [score_repository(health_input(i))["score"] for i in items]
        out.append({
            "owner": owner, "repositories": len(items),
            "stars": sum(int(i["stars"] or 0) for i in items),
            "commits_window": sum(int(i["commits_window"] or 0) for i in items),
            "prs_merged_window": sum(int(i["prs_merged_window"] or 0) for i in items),
            "open_issues": sum(int(i["issues_open"] or 0) for i in items),
            "avg_health_score": round(sum(scores) / len(scores), 1),
            "median_merge_hours": _median([i["median_merge_hours"] for i in items]),
        })
    out.sort(key=lambda x: -x["commits_window"])
    return {"days": days, "items": out}


@router.get("/notifications", tags=["notifications"])
def notifications(principal: Viewer, conn: Conn):
    items = []
    anomalies = portfolio_anomalies(conn, priv=principal.can_see_private, days=60)
    for a in anomalies.get("anomalies", [])[:6]:
        items.append({
            "id": f"anomaly-{a['repo_full_name']}-{a['date']}", "type": "anomaly", "severity": a["severity"],
            "title": f"{a['type'].replace('_', ' ').title()} in {a['repo_full_name']}",
            "message": a["explanation"], "created_at": a["date"], "link": f"/repos/{a['repo_full_name']}",
        })
    runs = q.recent_runs(conn, limit=5)
    for r in runs:
        if r["status"] in ("failed", "partial"):
            items.append({
                "id": f"run-{r['id']}", "type": "pipeline", "severity": "high" if r["status"] == "failed" else "medium",
                "title": f"Pipeline run #{r['id']} {r['status']}",
                "message": (r.get("error") or "Some repositories or quality checks need attention.")[:300],
                "created_at": (r["finished_at"] or r["created_at"]).isoformat() if (r["finished_at"] or r["created_at"]) else None,
                "link": "/pipelines",
            })
    return {"items": items, "unread": len(items)}


def _ensure_visible(conn, fn: str, principal) -> None:
    exists = q.repo_summary(conn, fn, principal.can_see_private, days=30)
    if not exists:
        raise HTTPException(404, "repository not found or not visible to your role")

