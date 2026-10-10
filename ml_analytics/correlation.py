"""Correlation analysis between daily activity metrics (Pearson + Spearman with p-values)."""

from __future__ import annotations

import pandas as pd
from scipy import stats

DEFAULT_METRICS = ["commits", "issues_opened", "issues_closed", "prs_opened", "prs_merged", "stars_gained"]


def correlation_matrix(df: pd.DataFrame, metrics: list[str] | None = None, min_points: int = 30) -> dict:
    metrics = [m for m in (metrics or DEFAULT_METRICS) if m in df.columns]
    n = len(df)
    if n < min_points or len(metrics) < 2:
        return {"status": "insufficient_data", "history_points": n, "pairs": [],
                "reason": f"need at least {min_points} days and two non-constant metrics"}
    pairs = []
    for i, a in enumerate(metrics):
        for b in metrics[i + 1:]:
            x, y = df[a].astype(float), df[b].astype(float)
            if x.std() == 0 or y.std() == 0:
                continue
            pr, pp = stats.pearsonr(x, y)
            sr, sp = stats.spearmanr(x, y)
            strength = "strong" if abs(sr) >= 0.6 else "moderate" if abs(sr) >= 0.3 else "weak"
            pairs.append({
                "metric_a": a, "metric_b": b,
                "pearson_r": round(float(pr), 3), "pearson_p": round(float(pp), 4),
                "spearman_rho": round(float(sr), 3), "spearman_p": round(float(sp), 4),
                "strength": strength,
                "significant": bool(sp < 0.05),
                "note": "association only - not causation",
            })
    pairs.sort(key=lambda p: -abs(p["spearman_rho"]))
    return {"status": "ok", "history_points": n, "metrics": metrics, "pairs": pairs}
