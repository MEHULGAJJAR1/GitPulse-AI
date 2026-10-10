"""PostgreSQL-backed ETag cache for the GitHub client (public.http_cache)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from sqlalchemy import Engine, text


class PgHttpCache:
    def __init__(self, engine: Engine):
        self.engine = engine

    def _get(self, url: str):
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT etag, body, next_link FROM http_cache WHERE url = :u"), {"u": url}
            ).first()
        return (row[0], row[1], row[2]) if row else None

    def _put(self, url: str, etag: str | None, body: Any, next_link: str | None) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO http_cache (url, etag, body, next_link, fetched_at)
                    VALUES (:u, :e, CAST(:b AS JSONB), :n, now())
                    ON CONFLICT (url) DO UPDATE SET etag = EXCLUDED.etag, body = EXCLUDED.body,
                      next_link = EXCLUDED.next_link, fetched_at = now()
                    """
                ),
                {"u": url, "e": etag, "b": json.dumps(body), "n": next_link},
            )

    async def get(self, url: str):
        return await asyncio.to_thread(self._get, url)

    async def put(self, url: str, etag: str | None, body: Any, next_link: str | None) -> None:
        if etag is None:  # nothing to revalidate against
            return
        await asyncio.to_thread(self._put, url, etag, body, next_link)
