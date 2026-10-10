"""Contributor activity patterns, bus-factor and (guarded) clustering of repositories."""

from __future__ import annotations

import numpy as np
import pandas as pd


def contributor_patterns(df: pd.DataFrame) -> dict:
    """df: columns login, commits_total, active_days (per repo). Returns concentration metrics."""
    if df.empty:
        return {"status": "insufficient_data", "reason": "no commits in the selected window"}
    c = df.sort_values("commits_total", ascending=False)
    total = float(c["commits_total"].sum()) or 1.0
    shares = c["commits_total"].astype(float) / total
    # Gini coefficient of commit distribution (0 = evenly spread, 1 = one person)
    x = np.sort(c["commits_total"].astype(float).to_numpy())
    n = len(x)
    gini = float((2 * np.sum((np.arange(1, n + 1)) * x) / (n * x.sum()) - (n + 1) / n)) if x.sum() > 0 and n > 0 else 0.0
    cum = shares.cumsum().to_numpy()
    bus_factor = int(np.searchsorted(cum, 0.5) + 1) if n else 0
    label = ("concentrated" if shares.iloc[0] >= 0.5 else "balanced" if gini < 0.4 else "skewed")
    return {
        "status": "ok",
        "contributors": n,
        "top_contributor": c.iloc[0]["login"],
        "top_share_pct": round(float(shares.iloc[0]) * 100, 1),
        "gini": round(gini, 3),
        "bus_factor_50pct": bus_factor,
        "pattern": label,
        "interpretation": (
            f"{bus_factor} contributor(s) account for half of all commits"
            + (" - a single-maintainer risk" if bus_factor <= 1 else "")
        ),
    }


def cluster_repositories(df: pd.DataFrame, features: list[str], min_repos: int = 6) -> dict:
    """KMeans over standardised repo features. Refuses to cluster with too few repositories."""
    if len(df) < min_repos:
        return {"status": "insufficient_data", "repos": len(df), "required": min_repos,
                "reason": f"clustering needs at least {min_repos} repositories; have {len(df)}", "clusters": []}
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler

    X = df[features].astype(float).fillna(0.0).to_numpy()
    Xs = StandardScaler().fit_transform(np.log1p(np.clip(X, 0, None)))
    k = 3 if len(df) >= 9 else 2
    km = KMeans(n_clusters=k, n_init=10, random_state=42).fit(Xs)
    out = []
    for cid in range(k):
        members = df.loc[km.labels_ == cid, "repo_full_name"].tolist()
        out.append({"cluster": cid, "repos": members, "size": len(members)})
    return {"status": "ok", "k": k, "features": features, "clusters": out,
            "note": "clusters describe similar activity profiles; they are not quality rankings"}
