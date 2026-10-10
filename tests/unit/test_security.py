"""Unit tests: API-key RBAC resolution, rate limiting and secret redaction."""
import hashlib

from app.config import Settings
from app.security import ROLE_RANK, SlidingWindowRateLimiter, resolve_role


def _settings(**kw) -> Settings:
    base = dict(
        api_keys_admin="admin-key-aaaaaaaa",
        api_keys_analyst="analyst-key-bbbbbbb",
        api_keys_viewer="viewer-key-ccccccc",
        github_token="ghp_secret_value_1234567890",
    )
    base.update(kw)
    return Settings(**base)


def test_resolves_each_role_by_its_key():
    s = _settings()
    assert resolve_role("admin-key-aaaaaaaa", s).role == "admin"
    assert resolve_role("analyst-key-bbbbbbb", s).role == "analyst"
    assert resolve_role("viewer-key-ccccccc", s).role == "viewer"


def test_unknown_or_missing_key_resolves_to_none():
    s = _settings()
    assert resolve_role(None, s) is None
    assert resolve_role("", s) is None
    assert resolve_role("guess", s) is None


def test_principal_exposes_fingerprint_not_key():
    s = _settings()
    p = resolve_role("viewer-key-ccccccc", s)
    assert p.key_fingerprint == hashlib.sha256(b"viewer-key-ccccccc").hexdigest()[:8]
    assert "viewer-key" not in p.key_fingerprint


def test_role_ranking_is_ordered():
    assert ROLE_RANK["viewer"] < ROLE_RANK["analyst"] < ROLE_RANK["admin"]


def test_rate_limiter_blocks_after_limit_and_reports_retry_after():
    rl = SlidingWindowRateLimiter(limit_per_minute=3)
    results = [rl.allow("10.0.0.1") for _ in range(4)]
    assert [ok for ok, _ in results] == [True, True, True, False]
    assert results[-1][1] >= 1
    # another client is unaffected
    assert rl.allow("10.0.0.2")[0] is True


def test_redacted_config_never_contains_secret_values():
    s = _settings()
    redacted = s.redacted_dict()
    flat = repr(redacted)
    assert "ghp_secret_value_1234567890" not in flat
    assert "admin-key-aaaaaaaa" not in flat
