"""Anomaly and outlier detection.

- Robust rolling z-score (median / MAD over a trailing window): sensitive to spikes and declines,
  resistant to the anomalies it is trying to find.
- Isolation Forest on [value, deviation from 7-day mean, weekday] - used only when >= 60 points,
  and reported as corroboration rather than the sole signal.
- Sudden decline rule: value is <= 20% of the trailing median when that median is >= 10 (avoids
  flagging ordinary Poisson noise on small counts).
- Cross-sectional outliers (repositories vs. peers) via the IQR fence on log-scaled metrics.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

MAD_SCALE = 1.4826


def detect_anomalies(
    series: pd.Series,
    dates: pd.Series,
    window: int = 28,
    min_points: int = 14,
    z_threshold: float = 3.5,
    use_iforest: bool = True,
) -> dict:
    s = series.astype(float).reset_index(drop=True)
    d = pd.to_datetime(dates).reset_index(drop=True)
    n = len(s)
    if n < min_points:
        return {"status": "insufficient_data", "history_points": n, "required_points": min_points,
                "anomalies": [], "method": None,
                "reason": f"need at least {min_points} days of history for anomaly detection"}

    med = s.rolling(window, min_periods=min_points).median().shift(1)
    mad = (s - med).abs().rolling(window, min_periods=min_points).median().shift(1) * MAD_SCALE
    mad = mad.where(mad > 1e-9, s.rolling(window, min_periods=min_points).std().shift(1).fillna(1.0)).fillna(1.0)
    z = (s - med) / mad.replace(0, 1.0)
    z = z.fillna(0.0)

    flags = pd.Series(False, index=s.index)
    reasons: dict[int, str] = {}
    for i in range(n):
        if abs(z.iloc[i]) >= z_threshold:
            flags.iloc[i] = True
            reasons[i] = "spike" if z.iloc[i] > 0 else "decline"
        elif not np.isnan(med.iloc[i]) and med.iloc[i] >= 10 and s.iloc[i] <= 0.2 * med.iloc[i]:
            flags.iloc[i] = True
            reasons[i] = "sudden_decline"

    iforest_flags = pd.Series(False, index=s.index)
    iforest_used = False
    if use_iforest and n >= 60:
        from sklearn.ensemble import IsolationForest

        dev = s - s.rolling(7, min_periods=1).mean()
        X = np.column_stack([s.values, dev.values, pd.to_datetime(d).dt.dayofweek.values])
        model = IsolationForest(n_estimators=200, contamination=0.03, random_state=42)
        labels = model.fit_predict(X)
        iforest_flags = pd.Series(labels == -1, index=s.index)
        iforest_used = True

    out = []
    for i in range(n):
        if not flags.iloc[i]:
            continue
        zi = float(z.iloc[i])
        severity = "high" if abs(zi) >= 6 or reasons[i] == "sudden_decline" else "medium" if abs(zi) >= 4.5 else "low"
        out.append({
            "date": d.iloc[i].date().isoformat(),
            "value": float(s.iloc[i]),
            "expected": round(float(med.iloc[i]), 2) if not np.isnan(med.iloc[i]) else None,
            "z_score": round(zi, 2),
            "type": reasons[i],
            "severity": severity,
            "corroborated_by_isolation_forest": bool(iforest_flags.iloc[i]) if iforest_used else None,
            "explanation": _explain(reasons[i], float(s.iloc[i]), med.iloc[i], zi),
        })
    return {
        "status": "ok",
        "history_points": n,
        "method": "robust_z_score" + ("+isolation_forest" if iforest_used else ""),
        "threshold": z_threshold,
        "anomalies": out,
        "count": len(out),
    }


def _explain(kind: str, value: float, expected, z: float) -> str:
    exp = "n/a" if expected is None or (isinstance(expected, float) and np.isnan(expected)) else f"{float(expected):.1f}"
    if kind == "spike":
        return f"Value {value:.0f} is far above the trailing median ({exp}); robust z = {z:.1f}."
    if kind == "decline":
        return f"Value {value:.0f} is far below the trailing median ({exp}); robust z = {z:.1f}."
    return f"Value {value:.0f} dropped to <=20% of the trailing median ({exp})."


def iqr_outliers(df: pd.DataFrame, columns: list[str], min_rows: int = 5) -> dict:
    """Cross-sectional outliers per metric using Tukey fences on log1p-scaled values."""
    if len(df) < min_rows:
        return {"status": "insufficient_data", "reason": f"need at least {min_rows} repositories, have {len(df)}",
                "outliers": []}
    out = []
    for col in columns:
        if col not in df or df[col].isna().all():
            continue
        vals = np.log1p(df[col].astype(float).fillna(0.0).clip(lower=0))
        q1, q3 = vals.quantile(0.25), vals.quantile(0.75)
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        for idx, v in vals.items():
            if v < lo or v > hi:
                out.append({
                    "repo_full_name": df.loc[idx, "repo_full_name"],
                    "metric": col,
                    "value": float(df.loc[idx, col]),
                    "direction": "high" if v > hi else "low",
                    "fence": [round(float(np.expm1(lo)), 2), round(float(np.expm1(hi)), 2)],
                })
    return {"status": "ok", "outliers": out, "method": "tukey_iqr_log1p"}
