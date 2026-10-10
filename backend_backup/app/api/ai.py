"""AI analytics assistant. Answers are grounded in database results; an LLM only narrates them."""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.config import get_settings
from app.deps import Conn, Viewer
from app.services import insights as fallback
from app.services import queries as q
from app.services.analytics import portfolio_anomalies, portfolio_insights, repo_analysis
from app.services.llm import llm_status, narrate
from ml_analytics.health import score_repository
from app.services.analytics import health_input

router = APIRouter(prefix="/ai")


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    days: int = Field(default=30, ge=7, le=365)


@router.get("/status", tags=["ai"])
def ai_status(principal: Viewer):
    return {**llm_status(), "fallback": "rule_based",
            "note": "Rule-based answers are always available. LLM narration needs LLM_PROVIDER and LLM_API_KEY."}


@router.post("/ask", tags=["ai"])
async def ask(principal: Viewer, conn: Conn, body: AskRequest):
    priv = principal.can_see_private
    base = fallback.answer(conn, body.question, priv=priv, days=body.days)
    if not get_settings().llm_enabled:
        return {**base, "question": body.question}

    context = {
        "data_note": "Values come from GitPulse analytics tables. Rows with data_source=synthetic are demo data.",
        "rule_based_answer": base["answer"],
        "repositories": [
            {k: r[k] for k in ("repo_full_name", "data_source", "stars", "stars_gained_window", "commits_window",
                               "commits_30d", "issues_open", "prs_open", "median_merge_hours", "days_since_push",
                               "contributors_count") if k in r}
            for r in q.repo_summaries(conn, priv=priv, days=body.days)[:15]
        ],
        "anomalies": portfolio_anomalies(conn, priv=priv, days=60).get("anomalies", [])[:15],
        "portfolio": portfolio_insights(conn, priv=priv, days=body.days),
    }
    if base["repositories"]:
        a = repo_analysis(conn, base["repositories"][0], priv=priv, days=180)
        context["focus_repository"] = {"name": base["repositories"][0], "forecast": a.get("forecast"),
                                       "insights": a.get("insights"), "health": a.get("health")}
    text_out = await narrate(body.question, context)
    if text_out is None:
        return {**base, "question": body.question, "note": base["note"] + " LLM unavailable or failed; showing rule-based answer."}
    return {**base, "question": body.question, "answer": text_out, "mode": "llm", "llm_used": True,
            "note": "Narrated by the configured LLM from the grounded context below. Verify figures against the sources listed."}


@router.get("/insights", tags=["ai"])
async def insights(principal: Viewer, conn: Conn, repo: str | None = Query(None, pattern=r"^[A-Za-z0-9_.-]{1,39}/[A-Za-z0-9_.-]{1,100}$")):
    priv = principal.can_see_private
    if repo:
        a = repo_analysis(conn, repo, priv=priv, days=180)
        items = a.get("insights", [])
        ctx = {"repo": repo, "health": a.get("health"), "insights": items, "forecast_status": a.get("forecast", {}).get("status")}
    else:
        p = portfolio_insights(conn, priv=priv, days=30)
        items = []
        for name in [r["repo_full_name"] for r in q.repo_summaries(conn, priv=priv, days=30)][:10]:
            items += [{**i, "repo_full_name": name} for i in repo_analysis(conn, name, priv=priv, days=180).get("insights", [])]
        ctx = {"portfolio": p, "insights": items[:40]}
    order = {"high": 0, "medium": 1, "info": 2, "low": 3}
    items.sort(key=lambda i: order.get(i["severity"], 9))
    narrative = await narrate("Summarise the most important trends, anomalies, risks and recommendations. "
                              "Use only these insights.", ctx)
    if narrative is None:
        highs = [i for i in items if i["severity"] in ("high", "medium")][:5]
        if highs:
            lines = [f"- [{i['severity']}] {i['title']}: {i['evidence']} Recommendation: {i['recommendation']}" for i in highs]
            narrative = "Rule-based summary (no LLM configured). Priority findings:\n" + "\n".join(lines)
        else:
            narrative = "Rule-based summary (no LLM configured). No high or medium priority findings for the analysed repositories."
    return {"repo_full_name": repo, "insights": items, "narrative": narrative,
            "mode": "llm" if narrative and not narrative.startswith("Rule-based") else "rule_based"}
