"""Asynchronous GitHub REST API client.

Features
- httpx.AsyncClient with official headers (Accept, X-GitHub-Api-Version, User-Agent)
- Optional token (Authorization: Bearer). Without a token GitHub's anonymous limit applies.
- Link-header pagination with a hard page cap per endpoint
- ETag / If-None-Match revalidation backed by a pluggable cache (PostgreSQL in production).
  A 304 response reuses the cached body (GitHub does not count 304s against the quota).
- Retries with exponential backoff + jitter for network errors, 5xx and secondary limits
- Rate-limit handling: honours Retry-After / X-RateLimit-Reset; waits when the reset is
  short, otherwise raises RateLimitExceeded so the pipeline can stop cleanly.
- Tokens are never logged; error messages are redacted.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

log = logging.getLogger("gitpulse.github")

STAR_ACCEPT = "application/vnd.github.star+json"
_LINK_NEXT = re.compile(r'<([^>]+)>;\s*rel="next"')


class GitHubError(Exception):
    """Non-retryable GitHub API failure."""


class NotFoundError(GitHubError):
    pass


class AuthRequiredError(GitHubError):
    """GitHub refused an endpoint without credentials (401 on an anonymous request).

    Optional datasets (e.g. stargazers) raise this; the extractor records a gap and keeps the repository."""


class RateLimitExceeded(GitHubError):
    def __init__(self, reset_at: int | None, message: str = "GitHub rate limit exceeded"):
        super().__init__(message)
        self.reset_at = reset_at


class CacheBackend(Protocol):
    async def get(self, url: str) -> tuple[str | None, Any, str | None] | None: ...
    async def put(self, url: str, etag: str | None, body: Any, next_link: str | None) -> None: ...


@dataclass
class ClientStats:
    requests: int = 0
    cache_hits: int = 0
    not_modified: int = 0
    retries: int = 0
    rate_limit_waits: int = 0
    last_remaining: int | None = None
    errors: list[str] = field(default_factory=list)


class GitHubClient:
    def __init__(
        self,
        *,
        token: str = "",
        base_url: str = "https://api.github.com",
        timeout: float = 20.0,
        max_retries: int = 4,
        rate_limit_max_wait: int = 90,
        cache: CacheBackend | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep=asyncio.sleep,
    ):
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "GitPulse-ELT/1.0",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.AsyncClient(base_url=base_url, headers=headers, timeout=timeout, transport=transport)
        self.max_retries = max_retries
        self.rate_limit_max_wait = rate_limit_max_wait
        self.cache = cache
        self.stats = ClientStats()
        self._sleep = sleep
        self.authenticated = bool(token)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> GitHubClient:
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()

    # ------------------------------------------------------------------ core
    async def get(self, path_or_url: str, params: dict | None = None, accept: str | None = None) -> tuple[Any, str | None]:
        """Return (json_body, next_page_url). Handles cache, retries and rate limits."""
        url = self._full_url(path_or_url, params)
        cached = await self.cache.get(url) if self.cache else None
        headers: dict[str, str] = {}
        if accept:
            headers["Accept"] = accept
        if cached and cached[0]:
            headers["If-None-Match"] = cached[0]

        attempt = 0
        while True:
            attempt += 1
            self.stats.requests += 1
            try:
                resp = await self._client.get(url, headers=headers)
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                if attempt > self.max_retries:
                    raise GitHubError(f"network error after {attempt} attempts: {type(exc).__name__}") from exc
                await self._backoff(attempt, reason=type(exc).__name__)
                continue

            self.stats.last_remaining = _int_header(resp, "x-ratelimit-remaining", self.stats.last_remaining)

            if resp.status_code == 304 and cached is not None:
                self.stats.not_modified += 1
                return cached[1], cached[2]
            if resp.status_code == 200:
                body = resp.json()
                next_link = _next_link(resp)
                if self.cache:
                    await self.cache.put(url, resp.headers.get("etag"), body, next_link)
                return body, next_link
            if resp.status_code == 404:
                raise NotFoundError(f"not found: {_safe_path(url)}")
            if resp.status_code == 401:
                if not self.authenticated:
                    raise AuthRequiredError(f"{_safe_path(url)} requires authentication (anonymous request refused)")
                raise GitHubError("GitHub rejected the configured token (401). Check GITHUB_TOKEN.")
            if resp.status_code in (403, 429):
                wait = _rate_limit_wait(resp)
                if wait is not None:
                    reset_at = int(time.time() + wait)
                    if wait > self.rate_limit_max_wait:
                        raise RateLimitExceeded(reset_at, f"rate limit resets in {int(wait)}s (> max wait)")
                    self.stats.rate_limit_waits += 1
                    log.warning("rate limited; sleeping %.0fs", wait)
                    await self._sleep(wait)
                    continue
                if resp.status_code == 403:
                    raise GitHubError(f"forbidden ({_safe_path(url)}): {_message(resp)}")
            if resp.status_code >= 500 and attempt <= self.max_retries:
                await self._backoff(attempt, reason=f"HTTP {resp.status_code}")
                continue
            raise GitHubError(f"HTTP {resp.status_code} for {_safe_path(url)}: {_message(resp)}")

    async def paginate(
        self, path: str, params: dict | None = None, max_pages: int = 1, accept: str | None = None
    ) -> AsyncIterator[tuple[int, list[Any]]]:
        """Yield (page_number, items) following Link: rel=next up to max_pages."""
        url: str | None = self._full_url(path, {"per_page": 100, **(params or {})})
        page = 0
        while url and page < max_pages:
            page += 1
            body, next_link = await self.get(url, accept=accept)
            items = body if isinstance(body, list) else body.get("items", []) if isinstance(body, dict) else []
            yield page, items
            url = next_link

    # --------------------------------------------------------------- helpers
    def _full_url(self, path_or_url: str, params: dict | None) -> str:
        if path_or_url.startswith("http"):
            url = path_or_url
            if params:  # only applied for the first page; next links already carry their query
                sep = "&" if "?" in url else "?"
                url = url + sep + "&".join(f"{k}={v}" for k, v in params.items())
            return url
        base = str(self._client.base_url).rstrip("/")
        query = ""
        if params:
            from urllib.parse import urlencode

            query = "?" + urlencode({k: v for k, v in params.items() if v is not None})
        return f"{base}{path_or_url}{query}"

    async def _backoff(self, attempt: int, reason: str) -> None:
        self.stats.retries += 1
        delay = min(30.0, (2 ** (attempt - 1)) * 1.0) + random.uniform(0, 0.5)
        log.warning("retrying GitHub request (%s) in %.1fs, attempt %d", reason, delay, attempt)
        await self._sleep(delay)


def _int_header(resp: httpx.Response, name: str, default: int | None) -> int | None:
    value = resp.headers.get(name)
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default


def _next_link(resp: httpx.Response) -> str | None:
    link = resp.headers.get("link", "")
    match = _LINK_NEXT.search(link)
    return match.group(1) if match else None


def _rate_limit_wait(resp: httpx.Response) -> float | None:
    """Seconds to wait if this 403/429 is a rate-limit response, else None."""
    retry_after = resp.headers.get("retry-after")
    if retry_after:
        try:
            return float(retry_after) + 1
        except ValueError:
            pass
    if resp.headers.get("x-ratelimit-remaining") == "0":
        reset = _int_header(resp, "x-ratelimit-reset", None)
        if reset is not None:
            return max(1.0, reset - time.time() + 1)
    if resp.status_code == 429:
        return 60.0
    if "rate limit" in _message(resp).lower():
        return 60.0
    return None


def _message(resp: httpx.Response) -> str:
    try:
        return str(resp.json().get("message", ""))[:200]
    except Exception:  # noqa: BLE001
        return resp.text[:200]


def _safe_path(url: str) -> str:
    return url.split("?", 1)[0].replace("https://api.github.com", "")
