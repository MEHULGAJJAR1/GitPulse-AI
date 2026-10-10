"""Unit tests for GitHub REST helpers: pagination links, rate-limit detection, retry headers."""
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data_pipeline"))

from gitpulse_elt.github_client import _next_link, _rate_limit_wait  # noqa: E402


def _resp(headers: dict[str, str], status: int = 403) -> httpx.Response:
    return httpx.Response(status, headers=headers)


def test_next_link_is_extracted_from_pagination_header():
    link = '<https://api.github.com/repos/a/b/issues?page=2>; rel="next", <https://api.github.com/repos/a/b/issues?page=9>; rel="last"'
    assert _next_link(_resp({"link": link}, 200)) == "https://api.github.com/repos/a/b/issues?page=2"


def test_no_next_link_on_last_page():
    link = '<https://api.github.com/x?page=1>; rel="prev"'
    assert _next_link(_resp({"link": link}, 200)) is None


def test_retry_after_header_is_honoured_with_margin():
    assert _rate_limit_wait(_resp({"retry-after": "30"}, 429)) == 31.0


def test_primary_rate_limit_exhaustion_waits_until_reset():
    wait = _rate_limit_wait(_resp({"x-ratelimit-remaining": "0", "x-ratelimit-reset": "9999999999"}))
    assert wait is not None and wait > 0


def test_ordinary_403_is_not_treated_as_rate_limit():
    assert _rate_limit_wait(_resp({"x-ratelimit-remaining": "42"})) is None
