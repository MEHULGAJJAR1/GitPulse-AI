"""Regression tests for the production-readiness fixes.

- Analytics-backed queries must return empty results (not HTTP 500) before the ELT transform has built
  the `analytics` schema.
- An anonymous 401 from GitHub on an optional endpoint must be a distinct, recoverable error.
- Contributor rankings must fall back to GitHub's all-time contribution counts when commit history is outside the window.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.services import queries as q
from gitpulse_elt.github_client import AuthRequiredError, GitHubClient


class _ExplodingConn:
    """Any SQL execution fails the test: the guard must short-circuit before touching the database."""

    def execute(self, *_a, **_k):  # pragma: no cover - only hit on a regression
        raise AssertionError("query executed although analytics schema is missing")


def test_analytics_queries_short_circuit_when_schema_missing(monkeypatch):
    monkeypatch.setattr(q, "analytics_ready", lambda conn: False)
    conn = _ExplodingConn()
    assert q.repo_summaries(conn, priv=False) == []
    assert q.repo_summary(conn, "octocat/Hello-World", priv=False) is None
    assert q.contributor_ranking(conn, priv=False) == []
    assert q.repo_contributors(conn, "octocat/Hello-World", False) == []
    assert q.commits_page(conn, "octocat/Hello-World", days=30, limit=10, offset=0) == ([], 0)
    assert q.pr_cycle(conn, priv=False, days=30, repo=None) == {"weekly": [], "merge_hours": []}
    assert q.previous_window_commits(conn, priv=False, days=30) == 0
    assert q.visible_contributor_count(conn, priv=False) == 0


def test_anonymous_401_on_optional_endpoint_is_auth_required():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Requires authentication"})

    async def run():
        client = GitHubClient(token="", transport=httpx.MockTransport(handler), sleep=_no_sleep)
        try:
            await client.get("/repos/octocat/Hello-World/stargazers")
        finally:
            await client.aclose()

    with pytest.raises(AuthRequiredError) as info:
        asyncio.run(run())
    assert "requires authentication" in str(info.value)
    assert "Bearer" not in str(info.value)


def test_configured_token_rejected_is_reported_as_token_problem():
    from gitpulse_elt.github_client import GitHubError

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Bad credentials"})

    async def run():
        client = GitHubClient(token="ghp_test_value", transport=httpx.MockTransport(handler), sleep=_no_sleep)
        try:
            await client.get("/user")
        finally:
            await client.aclose()

    with pytest.raises(GitHubError) as info:
        asyncio.run(run())
    assert not isinstance(info.value, AuthRequiredError)
    assert "Check GITHUB_TOKEN" in str(info.value)
    assert "ghp_test_value" not in str(info.value)


async def _no_sleep(_seconds):
    return None
