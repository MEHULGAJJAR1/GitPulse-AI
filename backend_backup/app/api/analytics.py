"""Advanced analytics endpoints: forecasts, anomalies, change points, seasonality, correlation,
PR cycle time, issue aging, health portfolio, outliers, clusters and insights."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.config import get_settings
from app.deps import Conn, NamePath, OwnerPath, Viewer, full_name
from app.services import queries as q
from app.services.analytics import daily_frame, portfolio_anomalies, portfolio_health, portfolio_insights, repo_analysis
from app.services.cache import cached
from ml_analytics.timeseries import forecast_series, stats_to_json

router = APIRouter(prefix="/analytics")
Metric = Literal["commits", "stars", "issues_opened", "prs_merged"]


def _ensure(conn, fn, principal):
    if not q.repo_summary(conn, fn, principal.can_see_private, days=30):
        raise HTTPException(404, "repository not found or not visible to your role")


@router.get("/repos/{owner}/{name}", tags=["analytics"])
def repo_full_analysis(principal: Viewer, conn: Conn, owner: OwnerPath, name: NamePath,
                       days: int = Query(180, ge=14, le=730), metric: Metric = "commits"):
    """Everything for one repository: descriptive stats, trend, seasonality, forecast, anomalies,
    change points, correlations, contributor patterns, health and explainable insights."""
    fn = full_name(owner, name)
    _ensure(conn, fn, principal)
    key = f"repo-analysis:{fn}:{days}:{metric}:{principal.can_see_private}"
    ttl = get_settings().analytics_cache_ttl_seconds
    return cached(key, ttl, lambda: repo_analysis(conn, fn, priv=principal.can_see_private, days=days, metric=metric))


@router.get("/forecast/{owner}/{name}", tags=["analytics"])
def forecast(principal: Viewer, conn: Conn, owner: OwnerPath, name: NamePath,
             metric: Metric = "commits", horizon: int = Query(14, ge=7, le=60), days: int = Query(180, ge=14, le=730)):
    fn = full_name(owner, name)
    _ensure(conn, fn, principal)
    s = get_settings()
    df = daily_frame(conn, fn, days)
    col = {"commits": "commits", "stars": "stars_gained", "issues_opened": "issues_opened", "prs_merged": "prs_merged"}[metric]
    base = float(df["cumulative_stars_observed"].iloc[-1]) if metric == "stars" and not df.empty else None
    res = forecast_series(df[col] if not df.empty else [], df["activity_date"] if not df.empty else [],
                          horizon=horizon, min_points=s.min_points_forecast, cumulative_base=base)
    return {"repo_full_name": fn, "metric": metric, "is_prediction_note": "forecast rows are predictions, history rows are observations",
            **stats_to_json(res.payload)}


@router.get("/anomalies", tags=["analytics"])
def anomalies(principal: Viewer, conn: Conn, days: int = Query(90, ge=14, le=730), repo: str | None = Query(None, pattern=r"^[A-Za-z0-9_.-]{1,39}/[A-Za-z0-9_.-]{1,100}$")):
    if repo:
        _ensure(conn, repo, principal)
    return portfolio_anomalies(conn, priv=principal.can_see_private, days=days, repo=repo)


@router.get("/changepoints/{owner}/{name}", tags=["analytics"])
def changepoints(principal: Viewer, conn: Conn, owner: OwnerPath, name: NamePath, metric: Metric = "commits",
                 days: int = Query(365, ge=21, le=730)):
    fn = full_name(owner, name)
    _ensure(conn, fn, principal)
    from ml_analytics.changepoint import detect_changepoints

    df = daily_frame(conn, fn, days)
    col = {"commits": "commits", "stars": "stars_gained", "issues_opened": "issues_opened", "prs_merged": "prs_merged"}[metric]
    if df.empty:
        return {"status": "insufficient_data", "changepoints": [], "history_points": 0}
    return {"repo_full_name": fn, "metric": metric, **stats_to_json(detect_changepoints(df[col], df["activity_date"]))}


@router.get("/seasonality/{owner}/{name}", tags=["analytics"])
def seasonality(principal: Viewer, conn: Conn, owner: OwnerPath, name: NamePath, days: int = Query(365, ge=14, le=730)):
    fn = full_name(owner, name)
    _ensure(conn, fn, principal)
    from ml_analytics.timeseries import seasonality as seas, trend_slope

    df = daily_frame(conn, fn, days)
    if df.empty:
        return {"status": "insufficient_data"}
    return {"repo_full_name": fn, **stats_to_json(seas(df["commits"], df["activity_date"])),
            "trend": stats_to_json(trend_slope(df["commits"]))}


@router.get("/correlation/{owner}/{name}", tags=["analytics"])
def correlation(principal: Viewer, conn: Conn, owner: OwnerPath, name: NamePath, days: int = Query(365, ge=14, le=730)):
    fn = full_name(owner, name)
    _ensure(conn, fn, principal)
    from ml_analytics.correlation import correlation_matrix

    df = daily_frame(conn, fn, days)
    if df.empty:
        return {"status": "insufficient_data", "pairs": []}
    return {"repo_full_name": fn, **stats_to_json(correlation_matrix(df))}


@router.get("/pr-cycle", tags=["analytics"])
def pr_cycle(principal: Viewer, conn: Conn, days: int = Query(180, ge=7, le=730),
             repo: str | None = Query(None, pattern=r"^[A-Za-z0-9_.-]{1,39}/[A-Za-z0-9_.-]{1,100}$")):
    import numpy as np

    data = q.pr_cycle(conn, priv=principal.can_see_private, days=days, repo=repo)
    hours = np.array(data["merge_hours"], dtype=float)
    dist = {}
    if hours.size:
        dist = {"count": int(hours.size), "median_hours": round(float(np.median(hours)), 2),
                "p90_hours": round(float(np.percentile(hours, 90)), 2), "mean_hours": round(float(hours.mean()), 2),
                "within_24h_pct": round(float((hours <= 24).mean() * 100), 1),
                "over_7d_pct": round(float((hours > 168).mean() * 100), 1)}
        hist, edges = np.histogram(hours, bins=[0, 4, 12, 24, 72, 168, 720, 1e9])
        labels = ["<4h", "4-12h", "12-24h", "1-3d", "3-7d", "7-30d", ">30d"]
        dist["histogram"] = [{"bucket": l, "count": int(c)} for l, c in zip(labels, hist)]
    return {"days": days, "repo": repo, "distribution": dist, "weekly": data["weekly"],
            "status": "ok" if hours.size else "insufficient_data"}


@router.get("/issue-aging", tags=["analytics"])
def issue_aging(principal: Viewer, conn: Conn, repo: str | None = Query(None, pattern=r"^[A-Za-z0-9_.-]{1,39}/[A-Za-z0-9_.-]{1,100}$")):
    import numpy as np

    data = q.issue_aging(conn, priv=principal.can_see_private, repo=repo)
    res = data["resolution"]
    closed = [float(r["close_hours"]) for r in res if r["close_hours"] is not None]
    open_n = sum(1 for r in res if r["state"] == "open")
    resolution = {}
    if closed:
        arr = np.array(closed)
        resolution = {"closed_count": len(closed), "median_close_days": round(float(np.median(arr)) / 24, 2),
                      "p90_close_days": round(float(np.percentile(arr, 90)) / 24, 2),
                      "closed_within_7d_pct": round(float((arr <= 168).mean() * 100), 1)}
    return {"repo": repo, "open_issues": open_n, "buckets": data["buckets"], "resolution": resolution,
            "status": "ok" if res else "insufficient_data"}


@router.get("/health", tags=["analytics"])
def health_portfolio(principal: Viewer, conn: Conn, days: int = Query(30, ge=7, le=365)):
    items = portfolio_health(conn, priv=principal.can_see_private, days=days)
    items.sort(key=lambda x: x["score"])
    return {"items": stats_to_json(items), "method": items[0]["method"] if items else None}


@router.get("/portfolio", tags=["analytics"])
def portfolio(principal: Viewer, conn: Conn, days: int = Query(30, ge=7, le=365)):
    """Cross-repository analytics: IQR outliers, k-means activity clusters, stale/low-health lists."""
    return portfolio_insights(conn, priv=principal.can_see_private, days=days)


@router.get("/insights", tags=["analytics"])
def insights(principal: Viewer, conn: Conn, repo: str | None = Query(None, pattern=r"^[A-Za-z0-9_.-]{1,39}/[A-Za-z0-9_.-]{1,100}$"),
             days: int = Query(180, ge=14, le=730)):
    """Explainable findings. Each insight lists its evidence and the mart it came from."""
    if repo:
        _ensure(conn, repo, principal)
        a = repo_analysis(conn, repo, priv=principal.can_see_private, days=days)
        return {"repo_full_name": repo, "insights": a["insights"]}
    names = [r["repo_full_name"] for r in q.repo_summaries(conn, priv=principal.can_see_private, days=30)][:25]
    out = []
    for n in names:
        a = repo_analysis(conn, n, priv=principal.can_see_private, days=days)
        out += [{**i, "repo_full_name": n} for i in a["insights"]]
    order = {"high": 0, "medium": 1, "info": 2, "low": 3}
    out.sort(key=lambda i: order.get(i["severity"], 9))
    return {"repo_full_name": None, "insights": out, "repositories_analysed": len(names)}
