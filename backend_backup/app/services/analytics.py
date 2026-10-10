"""Orchestrates the statistical / ML analytics for a repository or the whole portfolio.

Every result carries `status` (ok | insufficient_data) and the number of observations used,
so the UI can show *why* something is missing rather than displaying an unreliable number.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from sqlalchemy.engine import Connection

from app.config import get_settings
from app.services import queries as q
from app.services.cache import cached
from ml_analytics.anomaly import detect_anomalies, iqr_outliers
from ml_analytics.changepoint import detect_changepoints
from ml_analytics.correlation import correlation_matrix
from ml_analytics.health import score_repository
from ml_analytics.patterns import cluster_repositories, contributor_patterns
from ml_analytics.timeseries import descriptive_stats, forecast_series, moving_averages, seasonality, stats_to_json, trend_slope


def _clean(obj):
    return stats_to_json(obj)


def _float(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def health_input(row: dict) -> dict:
    return {
        "repo_full_name": row["repo_full_name"],
        "commits_30d": row.get("commits_30d"),
        "commits_total": row.get("commits_total"),
        "pct_issues_closed_7d": _float(row.get("pct_issues_closed_7d")),
        "median_merge_hours": _float(row.get("median_merge_hours")),
        "days_since_push": _float(row.get("days_since_push")),
        "contributors_count": row.get("contributors_count"),
        "releases_count": row.get("releases_count"),
    }


def daily_frame(conn: Connection, full_name: str, days: int) -> pd.DataFrame:
    data = q.repo_timeseries(conn, full_name, days)
    df = pd.DataFrame(data)
    if df.empty:
        return pd.DataFrame(columns=["activity_date", "commits", "issues_opened", "issues_closed", "prs_opened", "prs_merged", "stars_gained"])
    df["activity_date"] = pd.to_datetime(df["activity_date"])
    return df


def portfolio_health(conn: Connection, *, priv: bool, days: int = 30) -> list[dict]:
    summaries = q.repo_summaries(conn, priv=priv, days=days)
    return [score_repository({**health_input(r), "commits_total": r["commits_total"]}) | {
        "stars": r["stars"], "language": r["language"], "data_source": r["data_source"]} for r in summaries]


def repo_analysis(conn: Connection, full_name: str, *, priv: bool, days: int = 180, metric: str = "commits") -> dict:
    s = get_settings()
    summary = q.repo_summary(conn, full_name, priv, days=30)
    if summary is None:
        return {"status": "not_found"}
    df = daily_frame(conn, full_name, days)
    dates = df["activity_date"] if not df.empty else pd.Series([], dtype="datetime64[ns]")
    series_map = {"commits": "commits", "stars": "stars_gained", "issues_opened": "issues_opened", "prs_merged": "prs_merged"}
    col = series_map.get(metric, "commits")
    values = df[col] if not df.empty else pd.Series([], dtype=float)

    cumulative_base = float(df["cumulative_stars_observed"].iloc[-1]) if (metric == "stars" and not df.empty) else None
    fc = forecast_series(values, dates, horizon=14, min_points=s.min_points_forecast, cumulative_base=cumulative_base)
    anomalies = detect_anomalies(values, dates, min_points=s.min_points_anomaly)
    cps = detect_changepoints(values, dates)
    seas = seasonality(values, dates) if not df.empty else {"status": "insufficient_data"}
    trend = trend_slope(values) if not df.empty else {"status": "insufficient_data"}
    ma = moving_averages(values) if not df.empty else None
    ma_tail = []
    if ma is not None:
        tail = ma.tail(60).copy()
        tail["date"] = dates.tail(60).dt.date.astype(str).values
        ma_tail = tail[["date", "value", "ma7", "ma28"]].replace({np.nan: None}).to_dict("records")
    corr = correlation_matrix(df) if not df.empty else {"status": "insufficient_data", "pairs": []}
    contributors = pd.DataFrame(q.repo_contributors(conn, full_name))
    patterns = contributor_patterns(contributors.rename(columns={"commits_total": "commits_total"})[["login", "commits_total", "active_days"]]) \
        if not contributors.empty else {"status": "insufficient_data", "reason": "no contributor data"}
    health = score_repository(health_input(summary))
    insights = build_insights(full_name, summary, health, trend, anomalies, cps, fc.payload, patterns, seas)
    return _clean({
        "repo_full_name": full_name,
        "window_days": days,
        "metric": metric,
        "descriptive": descriptive_stats(values),
        "moving_averages": ma_tail,
        "trend": trend,
        "seasonality": seas,
        "forecast": fc.payload,
        "anomalies": anomalies,
        "changepoints": cps,
        "correlation": corr,
        "contributor_patterns": patterns,
        "health": health,
        "insights": insights,
        "data_source": summary["data_source"],
        "is_synthetic": summary["data_source"] == "synthetic",
    })


def build_insights(full_name, summary, health, trend, anomalies, cps, fc, patterns, seas) -> list[dict]:
    """Deterministic, explainable findings. Each carries the evidence it is based on."""
    out: list[dict] = []

    def add(category, severity, title, evidence, recommendation, source):
        out.append({"id": f"{category}-{len(out) + 1}", "category": category, "severity": severity, "title": title,
                    "evidence": evidence, "recommendation": recommendation, "source": source})

    if health["score"] < 55:
        comp = health["components"][health["weakest_component"]]
        add("risk", "high", f"Low health score ({health['score']}, grade {health['grade']})",
            f"Weakest component: {health['weakest_component']} - {comp['explanation']}.",
            "Address the weakest component first; it has the largest headroom for score gain.", ["mart_repo_summary"])
    elif health["score"] >= 85:
        add("opportunity", "info", f"Strong health score ({health['score']}, grade {health['grade']})",
            "All components are close to their targets.", "Keep the cadence; consider publishing the practices that produce this result.",
            ["mart_repo_summary"])

    if trend.get("status") == "ok" and trend.get("direction") == "down" and (trend.get("pct_change_over_window") or 0) <= -20:
        add("trend", "medium", "Commit activity is declining",
            f"Linear trend {trend['slope_per_week']:+.2f} commits/week (p={trend['p_value']}), "
            f"about {trend['pct_change_over_window']:.0f}% over the window.",
            "Check for blocked work, reduced staffing, or a planned slowdown; compare with the forecast before acting.",
            ["mart_repo_daily"])
    if trend.get("status") == "ok" and trend.get("direction") == "up" and (trend.get("pct_change_over_window") or 0) >= 20:
        add("trend", "info", "Commit activity is growing",
            f"Linear trend {trend['slope_per_week']:+.2f} commits/week (p={trend['p_value']}).",
            "Watch review capacity: growing throughput often exposes merge-time bottlenecks.", ["mart_repo_daily"])

    recent = [a for a in anomalies.get("anomalies", []) if a["date"] >= (pd.Timestamp.utcnow().normalize() - pd.Timedelta(days=21)).date().isoformat()]
    for a in recent[:3]:
        add("anomaly", "high" if a["severity"] == "high" else "medium",
            f"Unusual {a['type'].replace('_', ' ')} on {a['date']}",
            a["explanation"] + (" Corroborated by Isolation Forest." if a.get("corroborated_by_isolation_forest") else ""),
            "Check releases, incidents or bulk operations on that date. Confirm whether the change is expected.",
            ["mart_repo_daily"])

    for cp in cps.get("changepoints", [])[-2:]:
        add("trend", "info", f"Structural change detected around {cp['date']}",
            f"Mean daily value moved from {cp['mean_before']} to {cp['mean_after']} "
            f"({cp['relative_change_pct']}%, p={cp['p_value']}).",
            "Correlate with team, process or release changes around that date.", ["mart_repo_daily"])

    mh = _float(summary.get("median_merge_hours"))
    if mh is not None and mh > 72:
        add("risk", "medium", f"Slow pull-request merges (median {mh:.0f}h)",
            f"{summary.get('prs_total', 0)} PRs analysed; median merge time exceeds 3 days.",
            "Introduce review SLAs, smaller PRs, or CODEOWNERS routing to shorten cycle time.", ["int_pr_cycle_times"])
    elif mh is not None and mh <= 24:
        add("opportunity", "info", f"Fast pull-request merges (median {mh:.0f}h)",
            "Merge latency is within a day.", "Maintain current review practices.", ["int_pr_cycle_times"])

    if (summary.get("issues_open") or 0) >= 10 and (_float(summary.get("avg_open_issue_age_days")) or 0) > 60:
        add("risk", "medium", "Aging issue backlog",
            f"{summary['issues_open']} open issues; average age {_float(summary['avg_open_issue_age_days']):.0f} days.",
            "Triage stale issues (label, close or assign) and set a monthly backlog review.", ["int_issue_resolution"])

    if patterns.get("status") == "ok" and patterns.get("bus_factor_50pct", 0) <= 1 and patterns.get("contributors", 0) >= 2:
        add("risk", "high", "Single-maintainer dependency",
            patterns["interpretation"] + f" (top contributor share {patterns['top_share_pct']}%).",
            "Pair-program on critical modules and document ownership to reduce bus factor.", ["mart_contributor_activity"])

    days_since = _float(summary.get("days_since_push"))
    if days_since is not None and days_since > 90:
        add("risk", "medium", f"No pushes for {days_since:.0f} days",
            "The repository has been dormant beyond the 90-day threshold.",
            "Confirm whether the project is maintained; archive it or schedule maintenance.", ["mart_repo_summary"])

    if fc.get("status") == "ok":
        rel = fc.get("reliability")
        if rel in ("low", "very_low"):
            add("forecast", "info", "Forecast reliability is low",
                f"Holdout MAE {fc['evaluation']['model_mae']} vs baseline {fc['evaluation']['baseline_mae']}.",
                "Do not plan capacity from this forecast; collect more history or use the baseline.", ["forecast"])
    elif fc.get("status") == "insufficient_data":
        add("forecast", "info", "Not enough history for a forecast",
            fc.get("reason", ""), "Keep the pipeline scheduled; forecasts unlock after enough daily history.", ["forecast"])

    if seas.get("status") == "ok" and (seas.get("strength") or 0) >= 0.6:
        add("trend", "info", f"Strong weekly seasonality (peak {seas['peak_day']})",
            f"Decomposition strength {seas['strength']}; lowest activity on {seas['lowest_day']}.",
            "Schedule releases and reviews around the peak day to reduce queueing.", ["mart_repo_daily"])
    return out


def portfolio_insights(conn: Connection, *, priv: bool, days: int) -> dict:
    summaries = q.repo_summaries(conn, priv=priv, days=days)
    scores = [score_repository(health_input(r)) for r in summaries]
    stale = [r["repo_full_name"] for r in summaries if (_float(r.get("days_since_push")) or 0) > 90]
    low = [s["repo_full_name"] for s in scores if s["score"] < 55]
    outl = iqr_outliers(pd.DataFrame(summaries), ["stars", "commits_window", "contributors_count", "issues_open"])
    clusters = cluster_repositories(
        pd.DataFrame(summaries).fillna(0), ["commits_window", "contributors_count", "issues_open", "prs_open"]) if summaries else {"status": "insufficient_data"}
    return _clean({"repos": len(summaries), "low_health": low, "stale": stale, "outliers": outl, "clusters": clusters})


def portfolio_anomalies(conn: Connection, *, priv: bool, days: int = 90, repo: str | None = None) -> dict:
    """Anomaly scan across repositories (commits metric) with a 60s cache per visibility."""
    key = f"anomalies:{priv}:{days}:{repo}"

    def compute():
        s = get_settings()
        names = [repo] if repo else [r["repo_full_name"] for r in q.repo_summaries(conn, priv=priv)]
        items, scanned, skipped = [], 0, 0
        for name in names:
            df = daily_frame(conn, name, days)
            if df.empty:
                skipped += 1
                continue
            res = detect_anomalies(df["commits"], df["activity_date"], min_points=s.min_points_anomaly)
            if res["status"] != "ok":
                skipped += 1
                continue
            scanned += 1
            for a in res["anomalies"]:
                items.append({**a, "repo_full_name": name, "metric": "commits"})
        items.sort(key=lambda a: (a["date"], abs(a["z_score"])), reverse=True)
        return {"status": "ok" if scanned else "insufficient_data", "window_days": days,
                "repos_scanned": scanned, "repos_skipped_insufficient_history": skipped,
                "anomalies": items[:200], "count": len(items), "metric": "commits"}

    return _clean(cached(key, get_settings().analytics_cache_ttl_seconds, compute))
