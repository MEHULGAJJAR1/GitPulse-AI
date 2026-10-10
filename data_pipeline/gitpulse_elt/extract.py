"""Extract + Load (raw) stage.

For each tracked target (repo, user or org) we:
  1. discover repositories (users/orgs expand to their most recently pushed repos)
  2. fetch repository metadata, languages, contributors, branches, releases
  3. fetch incremental deltas for commits, issues, pull requests and stargazers using
     sync_state cursors (watermarks) so re-runs only pull what is new
  4. write each object as raw JSON (deduplicated by content hash)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import Engine, text

from gitpulse_elt.github_client import STAR_ACCEPT, AuthRequiredError, GitHubClient, GitHubError, NotFoundError, RateLimitExceeded
from gitpulse_elt.store import RawStore, Record

log = logging.getLogger("gitpulse.extract")


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


@dataclass
class ExtractStats:
    repos_synced: int = 0
    repos_skipped: int = 0
    repos_failed: int = 0
    records: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    rate_limited: bool = False

    def add(self, entity: str, n: int) -> None:
        self.records[entity] = self.records.get(entity, 0) + n


class SyncStateStore:
    """Watermarks in public.sync_state (cursor = ISO timestamp, last_page = star pagination)."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def get(self, target: str, entity: str) -> tuple[str | None, int | None]:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT cursor, last_page FROM sync_state WHERE target=:t AND entity=:e"),
                {"t": target, "e": entity},
            ).first()
        return (row[0], row[1]) if row else (None, None)

    def set(self, target: str, entity: str, cursor: str | None = None, last_page: int | None = None) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO sync_state (target, entity, cursor, last_page, last_synced_at)
                    VALUES (:t, :e, :c, :p, now())
                    ON CONFLICT (target, entity) DO UPDATE SET
                      cursor = COALESCE(EXCLUDED.cursor, sync_state.cursor),
                      last_page = COALESCE(EXCLUDED.last_page, sync_state.last_page),
                      last_synced_at = now()
                    """
                ),
                {"t": target, "e": entity, "c": cursor, "p": last_page},
            )


class Extractor:
    def __init__(
        self,
        *,
        engine: Engine,
        client: GitHubClient,
        store: RawStore,
        settings,
        emit: Callable[[str, str, str], None],
    ):
        self.engine = engine
        self.client = client
        self.store = store
        self.settings = settings
        self.emit = emit  # emit(level, stage, message)
        self.state = SyncStateStore(engine)
        self.stats = ExtractStats()

    # ------------------------------------------------------------ discovery
    async def discover(self, kind: str, name: str) -> list[str]:
        cap = self.settings.discovery_max_repos
        if kind == "repo":
            return [name]
        if kind == "user":
            path = f"/users/{name}/repos"
            params = {"type": "owner", "sort": "pushed"}
        elif kind == "org":
            path = f"/orgs/{name}/repos"
            params = {"type": "public", "sort": "pushed"}
        else:
            raise ValueError(f"unknown target kind: {kind}")
        names: list[str] = []
        async for _, items in self.client.paginate(path, params, max_pages=max(1, (cap + 99) // 100)):
            for item in items:
                if not item.get("fork"):
                    names.append(item["full_name"])
                if len(names) >= cap:
                    break
            if len(names) >= cap:
                break
        return names

    # ------------------------------------------------------------ per repo
    async def sync_repo(self, full_name: str) -> None:
        s = self.settings
        repo = await self.client.get(f"/repos/{full_name}")
        repo_body = repo[0]
        if repo_body.get("private") and not s.allow_private_repos:
            self.stats.repos_skipped += 1
            self.emit("WARNING", "extract", f"skipped private repository {full_name} (ALLOW_PRIVATE_REPOS=false)")
            return
        self._write([Record("repository", full_name, full_name, repo_body)], "repository")

        # Languages (bytes per language) - one object per repo
        langs, _ = await self.client.get(f"/repos/{full_name}/languages")
        self._write([Record("language", full_name, full_name, {"repo": full_name, "languages": langs})], "language")

        # Contributors (capped)
        contrib_records = []
        async for _, items in self.client.paginate(f"/repos/{full_name}/contributors", max_pages=s.contributor_max_pages):
            contrib_records += [Record("contributor", f"{full_name}@{c['login']}", full_name, c) for c in items if c.get("login")]
        self._write(contrib_records, "contributor")

        # Branches and releases (latest 100)
        branch_records = []
        async for _, items in self.client.paginate(f"/repos/{full_name}/branches", max_pages=1):
            branch_records += [Record("branch", f"{full_name}@{b['name']}", full_name, b) for b in items]
        self._write(branch_records, "branch")

        release_records = []
        async for _, items in self.client.paginate(f"/repos/{full_name}/releases", max_pages=1):
            release_records += [Record("release", f"{full_name}@{r.get('tag_name') or r['id']}", full_name, r) for r in items]
        self._write(release_records, "release")

        await self._sync_commits(full_name)
        await self._sync_issues(full_name)
        await self._sync_pulls(full_name)
        try:
            await self._sync_stargazers(full_name)
        except AuthRequiredError as exc:
            # Stargazer history needs a token on GitHub. Keep the repository; stars_total still comes from the repo payload.
            self.emit("WARNING", "extract", f"stargazer history skipped for {full_name}: {exc}. Set GITHUB_TOKEN to ingest it.")
        self.stats.repos_synced += 1

    async def _sync_commits(self, full_name: str) -> None:
        cursor, _ = self.state.get(full_name, "commits")
        since = cursor or _iso(datetime.now(timezone.utc) - timedelta(days=self.settings.sync_lookback_days))
        newest: datetime | None = _parse(cursor)
        records: list[Record] = []
        async for _, items in self.client.paginate(
            f"/repos/{full_name}/commits", {"since": since}, max_pages=self.settings.commit_max_pages
        ):
            for c in items:
                records.append(Record("commit", f"{full_name}@{c['sha']}", full_name, c))
                ts = _parse((c.get("commit", {}).get("author") or {}).get("date"))
                if ts and (newest is None or ts > newest):
                    newest = ts
        self._write(records, "commit")
        if newest:
            self.state.set(full_name, "commits", cursor=_iso(newest))

    async def _sync_issues(self, full_name: str) -> None:
        cursor, _ = self.state.get(full_name, "issues")
        since = cursor or _iso(datetime.now(timezone.utc) - timedelta(days=self.settings.sync_lookback_days))
        newest = _parse(cursor)
        records: list[Record] = []
        async for _, items in self.client.paginate(
            f"/repos/{full_name}/issues",
            {"state": "all", "since": since, "sort": "updated", "direction": "desc"},
            max_pages=self.settings.issue_max_pages,
        ):
            for it in items:
                if "pull_request" in it:  # GitHub returns PRs from /issues too; they are ingested via /pulls
                    continue
                records.append(Record("issue", f"{full_name}#{it['number']}", full_name, it))
                ts = _parse(it.get("updated_at"))
                if ts and (newest is None or ts > newest):
                    newest = ts
        self._write(records, "issue")
        if newest:
            self.state.set(full_name, "issues", cursor=_iso(newest))

    async def _sync_pulls(self, full_name: str) -> None:
        cursor, _ = self.state.get(full_name, "pulls")
        watermark = _parse(cursor)
        newest = watermark
        records: list[Record] = []
        done = False
        async for _, items in self.client.paginate(
            f"/repos/{full_name}/pulls",
            {"state": "all", "sort": "updated", "direction": "desc"},
            max_pages=self.settings.pr_max_pages,
        ):
            for pr in items:
                ts = _parse(pr.get("updated_at"))
                if watermark and ts and ts <= watermark:
                    done = True  # results are sorted by updated desc: everything after is older
                    break
                records.append(Record("pull_request", f"{full_name}#{pr['number']}", full_name, pr))
                if ts and (newest is None or ts > newest):
                    newest = ts
            if done:
                break
        self._write(records, "pull_request")
        if newest:
            self.state.set(full_name, "pulls", cursor=_iso(newest))

    async def _sync_stargazers(self, full_name: str) -> None:
        """Stargazers are ordered by starred_at ascending. We resume from the last page reached."""
        _, last_page = self.state.get(full_name, "stargazers")
        start = max(1, last_page or 1)
        records: list[Record] = []
        page_reached = start
        last_len = 0
        pages = 0
        url = f"/repos/{full_name}/stargazers"
        page = start
        while pages < self.settings.star_max_pages:
            body, _ = await self.client.get(url, params={"per_page": 100, "page": page}, accept=STAR_ACCEPT)
            pages += 1
            page_reached = page
            last_len = len(body)
            for s in body:
                login = (s.get("user") or {}).get("login")
                if login:
                    records.append(Record("stargazer", f"{full_name}@{login}", full_name, s))
            if last_len < 100:
                break
            page += 1
        self._write(records, "stargazer")
        # If the final page was full we resume there next time; if partial, refetch it to catch new stars.
        self.state.set(full_name, "stargazers", last_page=page_reached)

    # ------------------------------------------------------------ helpers
    def _write(self, records: list[Record], entity: str) -> None:
        if records:
            self.store.write(records)
        self.stats.add(entity, len(records))


async def extract_targets(
    *,
    engine: Engine,
    client: GitHubClient,
    store: RawStore,
    settings,
    targets: list[tuple[str, str]],
    emit: Callable[[str, str, str], None],
    max_attempts: int = 3,
) -> ExtractStats:
    ex = Extractor(engine=engine, client=client, store=store, settings=settings, emit=emit)
    for kind, name in targets:
        try:
            repos = await ex.discover(kind, name)
            emit("INFO", "extract", f"{kind} {name}: discovered {len(repos)} repositories")
        except NotFoundError:
            emit("ERROR", "extract", f"{kind} '{name}' not found on GitHub")
            ex.stats.errors.append(f"{name}: not found")
            continue
        except RateLimitExceeded as exc:
            emit("ERROR", "extract", f"rate limit reached during discovery: {exc}")
            ex.stats.rate_limited = True
            break
        for full_name in repos:
            for attempt in range(1, max_attempts + 1):
                try:
                    await ex.sync_repo(full_name)
                    emit("INFO", "extract", f"synced {full_name}")
                    break
                except NotFoundError:
                    emit("WARNING", "extract", f"{full_name} not found or not accessible")
                    ex.stats.repos_failed += 1
                    break
                except RateLimitExceeded as exc:
                    emit("ERROR", "extract", f"rate limit: stopping extraction ({exc})")
                    ex.stats.rate_limited = True
                    ex.stats.errors.append(str(exc))
                    return ex.stats
                except (GitHubError, Exception) as exc:  # noqa: BLE001
                    if attempt >= max_attempts:
                        ex.stats.repos_failed += 1
                        ex.stats.errors.append(f"{full_name}: {exc}")
                        emit("ERROR", "extract", f"failed {full_name} after {attempt} attempts: {exc}")
                    else:
                        emit("WARNING", "extract", f"attempt {attempt} for {full_name} failed: {exc}; retrying")
                        await asyncio.sleep(2 ** attempt)
    ex.stats.records["_written_new"] = store.inserted
    ex.stats.records["_deduplicated"] = store.deduplicated
    return ex.stats
