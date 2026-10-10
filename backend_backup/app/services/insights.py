"""Fallback ("no LLM") answers grounded in database results.

When no LLM is configured, the assistant answers with deterministic templates filled from SQL
results. Every answer states that it is rule-based and lists the analytics sources it used, so the
user can verify the numbers. No statistic is produced that the database did not return.
"""

from __future__ import annotations

import re

from sqlalchemy.engine import Connection

from app.services import queries as q
from app.services.analytics import health_input, portfolio_anomalies, portfolio_health, repo_analysis
from ml_analytics.health import score_repository

INTENTS = [
    ("anomaly", r"anomal|spike|unusual|outlier|sudden|drop"),
    ("forecast", r"forecast|predict|next (week|month)|future|will .* (grow|increase|decline)"),
    ("health", r"health|score|grade|healthy|risk"),
    ("pr", r"pull request|\bprs?\b|merge|review"),
    ("issues", r"issue|backlog|bug|aging|ageing"),
    ("contributors", r"contributor|author|who |developer|bus factor|maintainer"),
    ("stars", r"star|growth|popular|fork"),
    ("languages", r"language"),
    ("ranking", r"top|rank|leaderboard|most|best|compare|which"),
]


def detect_intent(question: str) -> str:
    text = question.lower()
    for name, pattern in INTENTS:
        if re.search(pattern, text):
            return name
    return "overview"


def mentioned_repos(question: str, names: list[str]) -> list[str]:
    text = question.lower()
    found = [n for n in names if n.lower() in text or n.split("/")[-1].lower() in text]
    return found


def answer(conn: Connection, question: str, *, priv: bool, days: int = 30) -> dict:
    intent = detect_intent(question)
    summaries = q.repo_summaries(conn, priv=priv, days=days)
    names = [s["repo_full_name"] for s in summaries]
    targets = mentioned_repos(question, names)
    sources: list[str] = []
    lines: list[str] = []

    if not summaries:
        return _pack("No repositories are ingested yet. Run the pipeline (Pipelines page) to collect GitHub data.",
                     intent, ["stg_repositories"], [])

    if intent == "health":
        scores = sorted((score_repository(health_input(s)) | {"repo": s["repo_full_name"]} for s in summaries),
                        key=lambda x: x["score"])
        sel = [x for x in scores if x["repo"] in targets] or scores
        sources = ["mart_repo_summary"]
        for x in sel[:6]:
            weak = x["components"][x["weakest_component"]]
            lines.append(f"- {x['repo']}: health {x['score']} (grade {x['grade']}, confidence {x['confidence']}). "
                         f"Weakest: {x['weakest_component']} - {weak['explanation']}.")
        lines.insert(0, f"Health scores for {len(sel)} repositor{'y' if len(sel) == 1 else 'ies'} (lowest first):")

    elif intent == "anomaly":
        res = portfolio_anomalies(conn, priv=priv, days=max(days, 60), repo=targets[0] if targets else None)
        sources = ["stg_commits", "mart_repo_daily"]
        if res["status"] != "ok":
            lines.append("Not enough daily history to run anomaly detection (needs at least 14 days per repository).")
        elif not res["anomalies"]:
            lines.append(f"No anomalies detected in the last {res['window_days']} days across {res['repos_scanned']} repositories.")
        else:
            lines.append(f"Detected {res['count']} commit-activity anomalies across {res['repos_scanned']} repositories "
                         f"(robust z-score, window {res['window_days']} days). Most recent / strongest:")
            for a in res["anomalies"][:6]:
                lines.append(f"- {a['date']} {a['repo_full_name']}: {a['type'].replace('_', ' ')} "
                             f"({a['value']:.0f} commits vs typical {a['expected']}, severity {a['severity']}).")

    elif intent == "forecast":
        targets = targets or [s["repo_full_name"] for s in sorted(summaries, key=lambda s: -(s["commits_window"] or 0))[:3]]
        sources = ["mart_repo_daily", "ml_analytics.timeseries"]
        for name in targets[:3]:
            a = repo_analysis(conn, name, priv=priv, days=180, metric="commits")
            fc = a.get("forecast", {})
            if fc.get("status") != "ok":
                lines.append(f"- {name}: {fc.get('reason', 'insufficient data')}. No forecast is shown.")
            else:
                total = sum(r["predicted"] for r in fc["forecast"])
                ev = fc["evaluation"]
                lines.append(f"- {name}: ~{total:.0f} commits predicted over 14 days "
                             f"(model {fc['model']}; holdout MAE {ev['model_mae']} vs baseline {ev['baseline_mae']}; "
                             f"reliability {fc['reliability']}). Predictions are estimates, not observations.")
        lines.insert(0, "Forecasts (14-day horizon, with uncertainty intervals in the forecast chart):")

    elif intent == "stars":
        ranked = sorted(summaries, key=lambda s: -(s["stars_gained_window"] or 0))
        sources = ["mart_repo_daily", "mart_repo_summary"]
        lines.append(f"Stars gained in the last {days} days (observed stargazer events) and current totals:")
        for s in ranked[:6]:
            lines.append(f"- {s['repo_full_name']}: +{s['stars_gained_window']} gained; {s['stars']} total stars.")

    elif intent == "pr":
        sources = ["int_pr_cycle_times", "mart_repo_summary"]
        ranked = sorted([s for s in summaries if s["median_merge_hours"] is not None], key=lambda s: s["median_merge_hours"])
        lines.append("Pull-request merge time (median hours from open to merge):")
        for s in ranked[:6]:
            lines.append(f"- {s['repo_full_name']}: median {s['median_merge_hours']:.0f}h, p90 {s['p90_merge_hours'] or 0:.0f}h, "
                         f"{s['prs_open']} open PRs.")
        if not ranked:
            lines.append("No merged pull requests have been ingested yet.")

    elif intent == "issues":
        sources = ["int_issue_resolution", "mart_issue_aging"]
        for s in sorted(summaries, key=lambda s: -s["issues_open"])[:6]:
            age = s["avg_open_issue_age_days"]
            lines.append(f"- {s['repo_full_name']}: {s['issues_open']} open issues"
                         + (f", average age {age:.0f} days" if age is not None else "") + ".")
        lines.insert(0, "Open issue backlog by repository:")

    elif intent == "contributors":
        rank = q.contributor_ranking(conn, priv=priv, repo=targets[0] if targets else None, limit=8)
        sources = ["mart_contributor_activity"]
        lines.append("Top contributors by observed commits" + (f" in {targets[0]}" if targets else " across repositories") + ":")
        for r in rank:
            lines.append(f"- {r['login']}: {r['commits_total']} commits across {r['repos']} repo(s).")
        if not rank:
            lines.append("No contributor data is available yet.")

    elif intent == "languages":
        dist = q.language_distribution(conn, priv=priv)
        total = sum(d["bytes_total"] or 0 for d in dist) or 1
        sources = ["stg_languages"]
        lines.append("Language distribution by bytes of code:")
        for d in dist[:8]:
            lines.append(f"- {d['language']}: {100 * (d['bytes_total'] or 0) / total:.1f}% across {d['repos']} repo(s).")

    elif intent == "ranking":
        ranked = sorted(summaries, key=lambda s: -(s["commits_window"] or 0))
        sources = ["mart_repo_daily", "mart_repo_summary"]
        lines.append(f"Repository leaderboard by commits in the last {days} days:")
        for s in ranked[:8]:
            lines.append(f"- {s['repo_full_name']}: {s['commits_window']} commits, {s['prs_merged_window']} PRs merged, {s['stars']} stars.")

    else:
        sources = ["mart_repo_summary", "mart_repo_daily"]
        total_commits = sum(s["commits_window"] or 0 for s in summaries)
        lines.append(f"Portfolio snapshot: {len(summaries)} repositories, {sum(s['stars'] or 0 for s in summaries)} total stars, "
                     f"{total_commits} commits in the last {days} days, {sum(s['issues_open'] for s in summaries)} open issues, "
                     f"{sum(s['prs_open'] for s in summaries)} open pull requests.")
        lines.append("Try asking about: health, anomalies, forecasts, pull-request merge time, issue backlog, contributors, stars, languages, or a repository by name.")

    return _pack("\n".join(lines), intent, sorted(set(sources)), targets)


def _pack(text: str, intent: str, sources: list[str], targets: list[str]) -> dict:
    return {
        "answer": text,
        "intent": intent,
        "mode": "rule_based",
        "llm_used": False,
        "grounded_in": sources,
        "repositories": targets,
        "note": "Generated from database results with deterministic rules (no LLM configured).",
    }
