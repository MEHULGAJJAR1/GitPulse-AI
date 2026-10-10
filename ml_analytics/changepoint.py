"""Change-point detection by binary segmentation on the mean (Welch t-statistic).

Splits are only accepted when both segments have >= min_segment points and |t| exceeds the
threshold (a conservative stand-in for a formal likelihood test). Results are reported with the
before/after means so the change is interpretable, not just flagged.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def detect_changepoints(series: pd.Series, dates: pd.Series, min_segment: int = 7,
                        t_threshold: float = 4.0, max_points: int = 3, min_points: int = 21) -> dict:
    s = series.astype(float).reset_index(drop=True).to_numpy()
    d = pd.to_datetime(dates).reset_index(drop=True)
    n = len(s)
    if n < min_points:
        return {"status": "insufficient_data", "history_points": n, "changepoints": [],
                "reason": f"need at least {min_points} days for change-point analysis"}

    found: list[int] = []

    def best_split(lo: int, hi: int):
        best = (0.0, None)
        for t in range(lo + min_segment, hi - min_segment + 1):
            a, b = s[lo:t], s[t:hi]
            if np.std(a) == 0 and np.std(b) == 0:
                continue
            tstat = stats.ttest_ind(a, b, equal_var=False).statistic
            if np.isfinite(tstat) and abs(tstat) > abs(best[0]):
                best = (float(tstat), t)
        return best

    segments = [(0, n)]
    while segments and len(found) < max_points:
        lo, hi = segments.pop(0)
        tstat, t = best_split(lo, hi)
        if t is None or abs(tstat) < t_threshold:
            continue
        found.append(t)
        segments += [(lo, t), (t, hi)]

    cps = []
    bounds = sorted(found)
    for t in bounds:
        lo = max(0, max([b for b in [0, *bounds] if b < t]))
        hi = min(n, min([b for b in [*bounds, n] if b > t]))
        before, after = s[lo:t], s[t:hi]
        mb, ma = float(before.mean()), float(after.mean())
        cps.append({
            "date": d.iloc[t].date().isoformat(),
            "index": int(t),
            "mean_before": round(mb, 3),
            "mean_after": round(ma, 3),
            "relative_change_pct": round((ma - mb) / mb * 100, 1) if mb else None,
            "direction": "increase" if ma > mb else "decrease",
            "p_value": float(round(stats.ttest_ind(before, after, equal_var=False).pvalue, 6)),
        })
    return {"status": "ok", "history_points": n, "changepoints": cps, "method": "binary_segmentation_welch_t",
            "t_threshold": t_threshold}
