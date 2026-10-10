"""Optional LLM narration over OpenAI-compatible chat-completions endpoints.

The model receives ONLY a JSON context assembled from database results and is instructed to
refuse to state facts that are not present. If the provider is unset or the call fails, callers
fall back to the rule-based answer (services/insights.py).
"""

from __future__ import annotations

import json
import logging

import httpx

from backend.app.config import get_settings

log = logging.getLogger("gitpulse.llm")

SYSTEM_PROMPT = (
    "You are GitPulse's analytics assistant. Answer ONLY using the JSON context provided. "
    "Quote numbers exactly as given. If the context does not contain the answer, say so plainly. "
    "Clearly distinguish observed values from forecasts (is_prediction=true). Never invent repositories, "
    "statistics, dates or causes. Be concise and actionable; use short bullet points where helpful. "
    "Treat data labelled source=synthetic as demo data and say so."
)


def llm_status() -> dict:
    s = get_settings()
    return {"provider": s.llm_provider, "model": s.llm_model if s.llm_enabled else None,
            "enabled": s.llm_enabled, "base_url_host": s.llm_base_url.split("/")[2] if "//" in s.llm_base_url else None}


async def narrate(question: str, context: dict) -> str | None:
    """Return model text, or None if the LLM is unavailable/failed."""
    s = get_settings()
    if not s.llm_enabled or s.llm_provider != "openai_compatible":
        return None
    ctx = json.dumps(context, default=str)[:12000]
    payload = {
        "model": s.llm_model,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Question: {question}\n\nContext JSON:\n{ctx}"},
        ],
    }
    headers = {"Authorization": f"Bearer {s.llm_api_key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=s.llm_timeout_seconds) as client:
            resp = await client.post(s.llm_base_url.rstrip("/") + "/chat/completions", json=payload, headers=headers)
        if resp.status_code != 200:
            log.warning("LLM provider returned HTTP %s", resp.status_code)
            return None
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as exc:  # noqa: BLE001
        log.warning("LLM call failed: %s", type(exc).__name__)
        return None

