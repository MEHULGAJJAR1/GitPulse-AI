"""API tests against a running GitPulse API (default http://127.0.0.1:8000).

Skipped automatically when the server is not reachable, so `pytest` stays green on a bare checkout.
Set GITPULSE_API_URL and GITPULSE_TEST_KEYS=viewer,analyst,admin (keys, comma-separated) to run.
"""
import os

import httpx
import pytest

BASE = os.environ.get("GITPULSE_API_URL", "http://127.0.0.1:8000/api")
KEYS = dict(zip(["viewer", "analyst", "admin"], os.environ.get("GITPULSE_TEST_KEYS", "").split(",")))


def _up() -> bool:
    try:
        return httpx.get(f"{BASE}/health", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(not _up(), reason="GitPulse API not running")


def _h(role: str = "viewer") -> dict:
    return {"X-API-Key": KEYS[role]} if KEYS.get(role) else {}


def test_health_is_public_and_secret_free():
    r = httpx.get(f"{BASE}/health", timeout=5)
    assert r.status_code == 200
    body = r.text
    assert "api_key" not in body.lower() and "password" not in body.lower()


def test_protected_routes_require_a_key():
    assert httpx.get(f"{BASE}/dashboard/overview", timeout=5).status_code == 401
    assert httpx.get(f"{BASE}/dashboard/overview", headers={"X-API-Key": "wrong"}, timeout=5).status_code == 401


@pytest.mark.skipif(not KEYS.get("viewer"), reason="viewer key not provided")
def test_overview_reports_data_mode_and_labels_sources():
    r = httpx.get(f"{BASE}/dashboard/overview?days=30", headers=_h("viewer"), timeout=20)
    assert r.status_code == 200
    body = r.json()
    assert body["data_mode"]["mode"] in {"live", "synthetic", "mixed", "empty"}
    for row in body["leaderboard"]:
        assert row["data_source"] in {"github", "synthetic"}


@pytest.mark.skipif(not KEYS.get("viewer"), reason="viewer key not provided")
def test_forecast_endpoint_returns_status_even_without_history():
    r = httpx.get(f"{BASE}/analytics/forecast/octocat/Hello-World?horizon=14", headers=_h("viewer"), timeout=30)
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        assert r.json()["status"] in {"ok", "insufficient_data"}


@pytest.mark.skipif(not KEYS.get("viewer"), reason="viewer key not provided")
@pytest.mark.parametrize("bad", ["../etc", "a/../etc", ".hidden/x"])
def test_target_names_with_traversal_are_rejected(bad):
    r = httpx.post(f"{BASE}/pipeline/targets", json={"kind": "repo", "name": bad},
                   headers=_h("admin") or _h("viewer"), timeout=10)
    assert r.status_code in (403, 422), r.text


@pytest.mark.skipif(not KEYS.get("viewer"), reason="viewer key not provided")
def test_viewer_cannot_start_a_pipeline_run():
    r = httpx.post(f"{BASE}/pipeline/runs", json={"mode": "github"}, headers=_h("viewer"), timeout=10)
    assert r.status_code == 403


@pytest.mark.skipif(not KEYS.get("viewer"), reason="viewer key not provided")
def test_ai_answer_is_grounded_and_marked():
    r = httpx.post(f"{BASE}/ai/ask", json={"question": "Which repo has the most commits?", "days": 30},
                   headers=_h("viewer"), timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] in {"rule_based", "llm"}
    assert body["grounded_in"], "answers must cite the tables they used"


@pytest.mark.skipif(not KEYS.get("viewer"), reason="viewer key not provided")
def test_exports_carry_data_mode_metadata():
    r = httpx.get(f"{BASE}/exports/repos?format=json", headers=_h("viewer"), timeout=20)
    assert r.status_code == 200
    assert "data_mode" in r.json()["meta"]
