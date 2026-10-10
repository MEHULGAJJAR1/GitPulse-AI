"""Small thread-safe TTL cache for expensive analytics results (per process)."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

_store: dict[str, tuple[float, Any]] = {}
_lock = threading.Lock()


def cached(key: str, ttl: int, factory: Callable[[], Any]) -> Any:
    now = time.monotonic()
    with _lock:
        hit = _store.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    value = factory()
    with _lock:
        _store[key] = (now, value)
    return value


def invalidate_all() -> None:
    with _lock:
        _store.clear()
