"""DETERMINISTIC SYNTHETIC DEMO DATA - explicitly labelled fallback.

These payloads mimic GitHub REST response shapes so the same staging models process them,
but they are tagged `source_system = 'synthetic'`. Every API response that includes such
rows exposes `data_mode` / `data_source` so the UI can never present them as live GitHub data.

Generation is deterministic: the same seed and fixed anchor date always yield identical
payloads (and therefore identical content hashes), so re-seeding is idempotent.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import numpy as np

from gitpulse_elt.store import Record

SYNTHETIC_SOURCE = "synthetic"
DEMO_ANCHOR = datetime(2026, 10, 8, 0, 0, tzinfo=timezone.utc)  # fixed anchor => reproducible


@dataclass(frozen=True)
class DemoRepo:
    name: str
    language: str
    commit_rate: float  # commits/day baseline
    trend: float  # relative change over the window (e.g. 0.6 = +60%)
    issue_rate: float
    pr_rate: float
    star_rate: float
    events: tuple[tuple[int, int, float], ...] = ()  # (day_index, length_days, multiplier)
    contributors: tuple[str, ...] = ()


DEMO_REPOS = (
    DemoRepo("aurora-api", "Python", 3.0, 0.6, 0.9, 0.8, 2.4,
             events=((118, 2, 4.0),),  # deliberate traffic/commit spike for anomaly demo
             contributors=("ada-lovelace", "grace-h", "linus-t", "margaret-h", "ken-t")),
    DemoRepo("nebula-web", "TypeScript", 4.0, 0.3, 1.2, 1.4, 3.5,
             contributors=("sofia-r", "yuki-m", "amara-o", "ada-lovelace", "lucas-b", "ivy-c")),
    DemoRepo("quasar-ml", "Python", 2.5, -0.7, 0.6, 0.5, 0.9,  # sustained decline (risk)
             contributors=("grace-h", "priya-s", "tomas-k")),
    DemoRepo("atlas-cli", "Go", 1.0, 0.1, 0.4, 0.3, 0.6,
             events=((60, 1, 0.0),), contributors=("linus-t", "ken-t")),
)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class DemoBuild:
    records: list[Record] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def add(self, rec: Record) -> None:
        self.records.append(rec)
        self.counts[rec.entity_type] = self.counts.get(rec.entity_type, 0) + 1


def generate(days: int = 150, seed: int = 42) -> DemoBuild:
    build = DemoBuild()
    start = DEMO_ANCHOR - timedelta(days=days - 1)
    weekday = np.array([1.0, 1.15, 1.2, 1.15, 1.0, 0.55, 0.45])  # Mon..Sun activity profile

    for idx, repo in enumerate(DEMO_REPOS):
        rng = np.random.default_rng(seed + idx * 101)
        full = f"demo-org/{repo.name}"
        contributors = repo.contributors
        weights = np.array([1.0 / (1 + i) for i in range(len(contributors))])
        weights = weights / weights.sum()
        commit_counts: dict[str, int] = {c: 0 for c in contributors}
        n_commit = 0
        open_items = 0
        star_total = 0
        last_release_day = -14

        build.add(Record("language", full, full, {"repo": full, "languages": {repo.language: 120000 + idx * 5000, "Shell": 1800}}))
        build.add(Record("branch", f"{full}@main", full, {"name": "main", "protected": True}))

        for i in range(days):
            day = start + timedelta(days=i)
            dow = day.weekday()
            mult = 1.0
            for ev_day, length, m in repo.events:
                if ev_day <= i < ev_day + length:
                    mult = m
            if repo.name == "atlas-cli" and i >= 60:
                mult = 0.0 if i < 80 else 1.0  # two-week outage then recovery (change point)
            trend_factor = 1 + repo.trend * (i / max(days - 1, 1)) - (repo.trend * 0.5 if repo.trend < 0 else 0)
            lam = max(0.05, repo.commit_rate * trend_factor * weekday[dow] * mult)

            # Commits
            for _ in range(int(rng.poisson(lam))):
                author = contributors[int(rng.choice(len(contributors), p=weights))]
                hour = int(rng.integers(7, 23))
                ts = day.replace(hour=hour, minute=int(rng.integers(0, 60)), second=int(rng.integers(0, 60)))
                sha = hashlib.sha1(f"{full}|{i}|{author}|{n_commit}|{seed}".encode()).hexdigest()
                n_commit += 1
                commit_counts[author] += 1
                build.add(Record("commit", f"{full}@{sha}", full, {
                    "sha": sha,
                    "commit": {"author": {"name": author, "email": f"{author}@example.invalid", "date": _iso(ts)},
                               "message": f"{['feat', 'fix', 'chore', 'refactor'][int(rng.integers(0, 4))]}: synthetic change {i}"},
                    "author": {"login": author},
                    "html_url": f"https://example.invalid/{full}/commit/{sha}",
                }))

            # Issues
            for n in range(int(rng.poisson(repo.issue_rate))):
                num = i * 100 + n + 1
                opened = day.replace(hour=int(rng.integers(0, 24)))
                author = contributors[int(rng.integers(0, len(contributors)))]
                close_days = float(rng.lognormal(mean=1.3, sigma=0.9))
                closed_at = opened + timedelta(days=close_days)
                is_closed = closed_at <= DEMO_ANCHOR
                if not is_closed:
                    open_items += 1
                build.add(Record("issue", f"{full}#{num}", full, {
                    "number": num, "title": f"Synthetic issue {num}", "state": "closed" if is_closed else "open",
                    "created_at": _iso(opened), "updated_at": _iso(closed_at if is_closed else DEMO_ANCHOR),
                    "closed_at": _iso(closed_at) if is_closed else None,
                    "user": {"login": author}, "comments": int(rng.integers(0, 8)),
                    "labels": [{"name": "bug" if n % 2 else "enhancement"}],
                }))

            # Pull requests
            for n in range(int(rng.poisson(repo.pr_rate))):
                num = 5000 + i * 100 + n
                opened = day.replace(hour=int(rng.integers(0, 24)))
                author = contributors[int(rng.integers(0, len(contributors)))]
                merge_hours = float(rng.lognormal(mean=np.log(18), sigma=1.0))
                closed_at = opened + timedelta(hours=merge_hours)
                if closed_at > DEMO_ANCHOR:
                    state, merged_at, closed = "open", None, None
                    open_items += 1
                elif rng.random() < 0.08:
                    state, merged_at, closed = "closed", None, _iso(closed_at)
                else:
                    state, merged_at, closed = "closed", _iso(closed_at), _iso(closed_at)
                build.add(Record("pull_request", f"{full}#{num}", full, {
                    "number": num, "title": f"Synthetic PR {num}", "state": state,
                    "created_at": _iso(opened), "updated_at": _iso(closed_at if closed else opened),
                    "closed_at": closed, "merged_at": merged_at, "draft": False,
                    "user": {"login": author}, "base": {"ref": "main"}, "head": {"ref": f"feature/{num}"},
                    "additions": int(rng.integers(5, 400)), "deletions": int(rng.integers(0, 120)),
                }))

            # Stargazers
            for _ in range(int(rng.poisson(repo.star_rate))):
                star_total += 1
                ts = day.replace(hour=int(rng.integers(0, 24)), minute=int(rng.integers(0, 60)))
                login = f"stargazer-{idx}-{star_total}"
                build.add(Record("stargazer", f"{full}@{login}", full, {
                    "starred_at": _iso(ts), "user": {"login": login, "id": 900000 + star_total},
                }))

            # Releases roughly every 2 weeks
            if i - last_release_day >= 14 and i > 20:
                last_release_day = i
                tag = f"v1.{i // 14}.0"
                build.add(Record("release", f"{full}@{tag}", full, {
                    "id": 1000 * idx + i, "tag_name": tag, "name": tag,
                    "published_at": _iso(day.replace(hour=15)), "prerelease": False, "draft": False,
                }))

        for login, n in commit_counts.items():
            build.add(Record("contributor", f"{full}@{login}", full, {"login": login, "contributions": n}))

        build.add(Record("repository", full, full, {
            "full_name": full, "name": repo.name, "owner": {"login": "demo-org"},
            "description": f"Synthetic demo repository ({repo.language})", "language": repo.language,
            "stargazers_count": star_total, "forks_count": max(0, star_total // 6),
            "open_issues_count": open_items, "watchers_count": star_total, "private": False, "fork": False,
            "archived": False, "default_branch": "main",
            "created_at": _iso(start - timedelta(days=400)), "pushed_at": _iso(DEMO_ANCHOR),
            "updated_at": _iso(DEMO_ANCHOR), "html_url": f"https://example.invalid/{full}",
            "license": {"spdx_id": "MIT"}, "topics": ["demo", "synthetic"], "size": 1000 + idx,
        }))
    return build
