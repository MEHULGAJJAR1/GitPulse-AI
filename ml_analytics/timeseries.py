"""Descriptive time-series analytics: moving averages, decomposition, forecasting with
uncertainty intervals and holdout evaluation against a naive baseline.

Forecast honesty rules
- Fewer than `min_points` observations -> status "insufficient_data" (no forecast returned).
- Every forecast is evaluated on a holdout window; the reliability label is derived from the
  error relative to a seasonal-naive baseline, and interval coverage is reported.
- Output always marks forecast rows with `is_prediction: true`; actuals carry `is_prediction: false`.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

Z80 = 1.2815515655446004
Z95 = 1.959963984540054
DISCLAIMER = (
    "Predictions are statistical estimates from past activity only. They do not account for planned "
    "work, releases or external events. Intervals are approximate."
)


@dataclass
class ForecastResult:
    status: str
    payload: dict


def moving_averages(series: pd.Series, windows=(7, 28)) -> pd.DataFrame:
    out = pd.DataFrame({"value": series.astype(float)})
    for w in windows:
        out[f"ma{w}"] = series.astype(float).rolling(w, min_periods=max(2, w // 2)).mean()
    return out


def descriptive_stats(series: pd.Series) -> dict:
    s = series.astype(float)
    if s.empty:
        return {"count": 0}
    return {
        "count": int(s.count()),
        "mean": round(float(s.mean()), 3),
        "median": round(float(s.median()), 3),
        "std": round(float(s.std(ddof=1)) if s.count() > 1 else 0.0, 3),
        "min": float(s.min()),
        "max": float(s.max()),
        "total": float(s.sum()),
        "zero_days_pct": round(float((s == 0).mean() * 100), 1),
    }


def trend_slope(series: pd.Series) -> dict:
    """Linear trend on daily values; reports slope per week and % change vs. window mean."""
    s = series.astype(float).reset_index(drop=True)
    n = len(s)
    if n < 14:
        return {"status": "insufficient_data", "points": n}
    x = np.arange(n)
    res = stats.linregress(x, s.values)
    mean = float(s.mean()) or 1e-9
    return {
        "status": "ok",
        "points": n,
        "slope_per_day": round(float(res.slope), 4),
        "slope_per_week": round(float(res.slope) * 7, 3),
        "pct_change_over_window": round(float(res.slope) * n / mean * 100, 1),
        "r_squared": round(float(res.rvalue) ** 2, 3),
        "p_value": round(float(res.pvalue), 4),
        "direction": "up" if res.slope > 0 and res.pvalue < 0.05 else "down" if res.slope < 0 and res.pvalue < 0.05 else "flat",
    }


def seasonality(series: pd.Series, dates: pd.Series, period: int = 7) -> dict:
    """Weekday profile + additive decomposition strength (STL-like, period=7)."""
    s = series.astype(float).reset_index(drop=True)
    d = pd.to_datetime(dates).reset_index(drop=True)
    overall = float(s.mean()) or 1e-9
    profile = s.groupby(d.dt.dayofweek).mean()
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    weekday = [
        {"day": names[i], "mean": round(float(profile.get(i, 0.0)), 3),
         "index": round(float(profile.get(i, 0.0)) / overall, 3)}
        for i in range(7)
    ]
    result: dict = {"weekday_profile": weekday, "status": "ok"}
    active_days = int((s > 0).sum())
    if len(s) < 2 * period or active_days < 10 or float(s.std()) == 0.0:
        result.update(status="insufficient_data", strength=None,
                      reason=(f"need at least {2 * period} daily points and 10 active days for decomposition "
                              f"(have {len(s)} points, {active_days} active)"))
        return result
    from statsmodels.tsa.seasonal import seasonal_decompose

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        dec = seasonal_decompose(s, model="additive", period=period, extrapolate_trend="freq")
    seas_plus_resid = dec.seasonal + dec.resid
    var_sr = float(np.var(seas_plus_resid, ddof=1)) or 1e-9
    strength = max(0.0, 1 - float(np.var(dec.resid, ddof=1)) / var_sr)
    peak = names[int(np.argmax(dec.seasonal.values[:period]))]
    low = names[int(np.argmin(dec.seasonal.values[:period]))]
    result.update(strength=round(strength, 3), peak_day=peak, lowest_day=low,
                  interpretation=("strong weekly seasonality" if strength >= 0.6
                                  else "moderate weekly seasonality" if strength >= 0.3
                                  else "weak weekly seasonality"))
    return result


# --------------------------------------------------------------------- forecasting
def _holt_fit(train: np.ndarray, horizon: int, seasonal: bool):
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = ExponentialSmoothing(
            train,
            trend="add",
            damped_trend=True,
            seasonal="add" if seasonal else None,
            seasonal_periods=7 if seasonal else None,
            initialization_method="estimated",
        )
        fit = model.fit(optimized=True)
        pred = np.asarray(fit.forecast(horizon), dtype=float)
        fitted = np.asarray(fit.fittedvalues, dtype=float)
    return pred, fitted


def _naive_baseline(train: np.ndarray, horizon: int) -> np.ndarray:
    """Seasonal-naive with weekly profile from the last 4 weeks (fallback: last-7-day mean)."""
    if len(train) >= 28:
        recent = train[-28:]
        profile = np.array([recent[i::7].mean() for i in range(7)])
        start = len(train) % 7
        return np.array([profile[(start + h) % 7] for h in range(horizon)])
    return np.full(horizon, train[-7:].mean() if len(train) >= 7 else train.mean())


def _metrics(actual: np.ndarray, pred: np.ndarray, lower: np.ndarray | None, upper: np.ndarray | None) -> dict:
    err = actual - pred
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err**2)))
    nz = actual != 0
    mape = float(np.mean(np.abs(err[nz] / actual[nz])) * 100) if nz.any() else None
    coverage = None
    if lower is not None and upper is not None:
        coverage = float(np.mean((actual >= lower) & (actual <= upper)))
    return {"mae": round(mae, 3), "rmse": round(rmse, 3),
            "mape_pct": round(mape, 2) if mape is not None else None,
            "coverage_80": round(coverage, 3) if coverage is not None else None}


def forecast_series(
    series: pd.Series,
    dates: pd.Series,
    horizon: int = 14,
    min_points: int = 28,
    cumulative_base: float | None = None,
) -> ForecastResult:
    """Forecast a daily count series. `cumulative_base` turns daily gains into a running total."""
    y = series.astype(float).fillna(0.0).to_numpy()
    d = pd.to_datetime(dates).reset_index(drop=True)
    n = len(y)
    if n < min_points:
        return ForecastResult("insufficient_data", {
            "status": "insufficient_data",
            "history_points": n,
            "required_points": min_points,
            "reason": f"only {n} days of history; at least {min_points} are needed for a reliable forecast",
            "disclaimer": DISCLAIMER,
        })
    if float(np.sum(y)) == 0:
        return ForecastResult("insufficient_data", {
            "status": "insufficient_data", "history_points": n, "reason": "no activity in the window",
            "disclaimer": DISCLAIMER,
        })

    # --- holdout evaluation to select the model
    holdout = int(min(14, max(7, n // 4)))
    train, test = y[:-holdout], y[-holdout:]
    candidates: dict[str, dict] = {}
    base_pred = _naive_baseline(train, holdout)
    baseline_mae = float(np.mean(np.abs(test - base_pred)))
    for name, seasonal in (("holt_damped", False), ("holt_winters_weekly", True)):
        if seasonal and len(train) < 21:
            continue
        try:
            pred, fitted = _holt_fit(train, holdout, seasonal)
            resid_sd = float(np.std(train[len(train) - len(fitted):] - fitted, ddof=1)) if len(fitted) > 2 else 1.0
            pred = np.clip(pred, 0, None)
            sigma = resid_sd * np.sqrt(np.arange(1, holdout + 1))
            lo80, hi80 = np.clip(pred - Z80 * sigma, 0, None), pred + Z80 * sigma
            candidates[name] = {"pred": pred, "m": _metrics(test, pred, lo80, hi80), "sigma_1": resid_sd}
        except Exception:  # noqa: BLE001 - a failed candidate is simply skipped
            continue
    if not candidates:
        return ForecastResult("insufficient_data", {"status": "insufficient_data", "history_points": n,
                                                     "reason": "model fitting did not converge", "disclaimer": DISCLAIMER})
    best = min(candidates, key=lambda k: candidates[k]["m"]["mae"])

    # --- refit on full history and forecast the horizon
    seasonal = best == "holt_winters_weekly"
    pred, fitted = _holt_fit(y, horizon, seasonal)
    pred = np.clip(pred, 0, None)
    resid_sd = float(np.std(y[len(y) - len(fitted):] - fitted, ddof=1)) if len(fitted) > 2 else 1.0
    steps = np.arange(1, horizon + 1)
    sigma = resid_sd * np.sqrt(steps)
    last_date = d.iloc[-1]
    rows = []
    cum = cumulative_base
    for i, p in enumerate(pred):
        date = (last_date + pd.Timedelta(days=i + 1)).date().isoformat()
        row = {
            "date": date,
            "is_prediction": True,
            "predicted": round(float(p), 3),
            "lower_80": round(max(0.0, float(p - Z80 * sigma[i])), 3),
            "upper_80": round(float(p + Z80 * sigma[i]), 3),
            "lower_95": round(max(0.0, float(p - Z95 * sigma[i])), 3),
            "upper_95": round(float(p + Z95 * sigma[i]), 3),
        }
        if cum is not None:
            cum = (cum or 0.0) + float(p)
            row["predicted_cumulative"] = round(cum, 1)
        rows.append(row)

    m = candidates[best]["m"]
    beats = m["mae"] < baseline_mae
    if n >= 60 and beats and (m["coverage_80"] or 0) >= 0.6:
        reliability = "moderate" if n < 120 else "good"
    elif beats:
        reliability = "low"
    else:
        reliability = "very_low"
    actual_hist = [{"date": d.iloc[i].date().isoformat(), "value": float(y[i]), "is_prediction": False}
                   for i in range(max(0, n - 90), n)]
    return ForecastResult("ok", {
        "status": "ok",
        "model": best,
        "history_points": n,
        "horizon_days": horizon,
        "history": actual_hist,
        "forecast": rows,
        "evaluation": {
            "holdout_days": holdout,
            "model_mae": m["mae"],
            "model_rmse": m["rmse"],
            "model_mape_pct": m["mape_pct"],
            "interval_coverage_80": m["coverage_80"],
            "baseline": "seasonal_naive" if n >= 28 else "moving_average",
            "baseline_mae": round(baseline_mae, 3),
            "improvement_over_baseline_pct": round((baseline_mae - m["mae"]) / baseline_mae * 100, 1) if baseline_mae > 0 else None,
            "candidates": {k: v["m"] for k, v in candidates.items()},
        },
        "reliability": reliability,
        "disclaimer": DISCLAIMER,
    })


def summarize_forecast(res: dict, label: str, unit: str = "commits") -> str:
    if res.get("status") != "ok":
        return f"{label}: {res.get('reason', 'insufficient data')}."
    total = sum(r["predicted"] for r in res["forecast"])
    ev = res["evaluation"]
    return (f"{label}: predicted ~{total:.0f} {unit} over the next {res['horizon_days']} days "
            f"(model {res['model']}, holdout MAE {ev['model_mae']} vs baseline {ev['baseline_mae']}, "
            f"reliability {res['reliability']}).")


def stats_to_json(obj):
    """Convert numpy types for JSON responses."""
    if isinstance(obj, dict):
        return {k: stats_to_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [stats_to_json(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        return None if math.isnan(float(obj)) or math.isinf(float(obj)) else float(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    return obj
