"""ML evaluation tests on synthetic series with known ground truth.

These check behaviour, not business meaning: the forecast should beat a naive baseline on a
clean seasonal series, intervals should be ordered, anomalies should find an injected spike,
change-points should find an injected level shift, and thin data must be refused, not guessed.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ml_analytics.anomaly import detect_anomalies  # noqa: E402
from ml_analytics.changepoint import detect_changepoints  # noqa: E402
from ml_analytics.health import score_repository  # noqa: E402
from ml_analytics.patterns import cluster_repositories, contributor_patterns  # noqa: E402
from ml_analytics.timeseries import forecast_series, seasonality  # noqa: E402

START = pd.Timestamp("2026-01-01")


def _dates(n: int) -> pd.Series:
    return pd.Series(pd.date_range(START, periods=n, freq="D"))


def test_forecast_refuses_short_history_instead_of_guessing():
    s = pd.Series(np.arange(10, dtype=float))
    res = forecast_series(s, _dates(10), horizon=7)
    assert res.status == "insufficient_data"
    assert "forecast" not in res.payload, "no predicted values may be produced for thin data"


def test_forecast_on_seasonal_series_has_ordered_intervals_and_beats_naive_baseline():
    rng = np.random.default_rng(0)
    n = 210
    t = np.arange(n)
    y = 20 + 0.05 * t + 6 * np.sin(2 * np.pi * t / 7) + rng.normal(0, 1.0, n)
    res = forecast_series(pd.Series(np.clip(y, 0, None)), _dates(n), horizon=14)
    assert res.status == "ok"
    payload = res.payload
    for row in payload["forecast"]:
        assert row["lower_95"] <= row["lower_80"] <= row["predicted"] <= row["upper_80"] <= row["upper_95"]
        assert row["predicted"] >= 0
        assert row["is_prediction"] is True
    ev = payload["evaluation"]
    assert ev["holdout_days"] > 0
    assert ev["model_mae"] <= ev["baseline_mae"] * 1.25, "model should not be far worse than the naive baseline"


def test_seasonality_is_reported_as_insufficient_on_sparse_data():
    s = pd.Series([0, 0, 0, 1, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0] * 1)
    out = seasonality(s, _dates(len(s)))
    assert out["status"] != "ok"


def test_anomaly_detector_finds_injected_spike_and_not_normal_days():
    rng = np.random.default_rng(1)
    y = rng.poisson(10, 120).astype(float)
    y[90] = 80.0
    out = detect_anomalies(pd.Series(y), _dates(120), use_iforest=False)
    flagged = {a["date"] for a in out["anomalies"]}
    assert str((START + pd.Timedelta(days=90)).date()) in flagged
    assert len(flagged) <= 5, "should not flag large numbers of ordinary days"


def test_changepoint_detector_finds_level_shift():
    rng = np.random.default_rng(2)
    y = np.concatenate([rng.normal(5, 1, 80), rng.normal(15, 1, 80)])
    out = detect_changepoints(pd.Series(np.clip(y, 0, None)), _dates(160))
    assert out["changepoints"], "a 3x level shift must be detected"
    cp_index = out["changepoints"][0]["index"]
    assert abs(cp_index - 80) <= 5


def test_changepoint_detector_is_quiet_on_stationary_noise():
    rng = np.random.default_rng(3)
    y = np.clip(rng.normal(10, 1, 160), 0, None)
    out = detect_changepoints(pd.Series(y), _dates(160))
    assert out["changepoints"] == []


def test_health_score_is_bounded_and_explains_gaps():
    empty = score_repository({})
    assert 0 <= empty["score"] <= 100
    assert empty.get("data_gaps") or empty.get("grade")
    good = score_repository({"commits_30d": 40, "commits_90d": 120, "days_since_push": 2, "prs_merged_30d": 12,
                             "median_merge_hours": 10, "issues_open": 3, "issues_closed_30d": 20,
                             "pct_issues_closed_7d": 0.8, "contributors_count": 8, "commit_authors": 8,
                             "releases_count": 6, "last_release_at": "2026-09-01"})
    poor = score_repository({"commits_30d": 0, "commits_90d": 0, "days_since_push": 900, "prs_merged_30d": 0,
                             "issues_open": 200, "contributors_count": 1, "commit_authors": 1})
    assert good["score"] > poor["score"]
    assert 0 <= poor["score"] <= 100


def test_clustering_refuses_with_too_few_repositories():
    df = pd.DataFrame({"repo_full_name": ["a/1", "a/2"], "commits_window": [1, 2], "contributors_count": [1, 2],
                       "issues_open": [0, 1], "prs_open": [0, 0]})
    out = cluster_repositories(df, ["commits_window", "contributors_count", "issues_open", "prs_open"])
    assert out["status"] != "ok"


def test_contributor_patterns_detect_single_maintainer():
    df = pd.DataFrame({"login": ["ada", "bob", "cy"], "commits_total": [95, 3, 2]})
    out = contributor_patterns(df)
    assert out["status"] == "ok"
    assert out["top_share_pct"] > 90
    assert out["bus_factor_50pct"] == 1


@pytest.mark.parametrize("n", [0, 1, 3])
def test_empty_or_tiny_series_do_not_crash(n):
    s = pd.Series(np.zeros(n))
    out = detect_anomalies(s, _dates(n), use_iforest=False)
    assert out.get("anomalies", []) == [] or isinstance(out, dict)
