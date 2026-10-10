"""Repository health score (0-100) with transparent, weighted components.

Every component is normalised to [0, 1] from a documented formula; the response lists each
component's raw value, score, weight and a plain-English explanation so the score is auditable.
A missing input is never silently treated as perfect: it contributes a neutral 0.5 and is flagged
in `data_gaps`.
"""

from __future__ import annotations

import math

WEIGHTS = {
    "activity": 0.25,
    "responsiveness": 0.20,
    "review_speed": 0.20,
    "maintenance": 0.15,
    "community": 0.10,
    "release_discipline": 0.10,
}


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def score_repository(row: dict) -> dict:
    gaps: list[str] = []
    comps: dict[str, dict] = {}

    c30 = float(row.get("commits_30d") or 0)
    comps["activity"] = {
        "raw": c30, "score": _clamp(c30 / 20.0), "weight": WEIGHTS["activity"],
        "explanation": f"{int(c30)} commits in the last 30 days (full marks at 20+)",
    }

    pct = row.get("pct_issues_closed_7d")
    if pct is None or (isinstance(pct, float) and math.isnan(pct)):
        gaps.append("no closed issues yet - responsiveness is neutral")
        s = 0.5
        pct_txt = "n/a"
    else:
        s = _clamp(float(pct))
        pct_txt = f"{float(pct) * 100:.0f}%"
    comps["responsiveness"] = {
        "raw": pct, "score": s, "weight": WEIGHTS["responsiveness"],
        "explanation": f"share of issues closed within 7 days: {pct_txt}",
    }

    mh = row.get("median_merge_hours")
    if mh is None or (isinstance(mh, float) and math.isnan(mh)):
        gaps.append("no merged pull requests - review speed is neutral")
        s = 0.5
        mh_txt = "n/a"
    else:
        mh = float(mh)
        # 24h -> 1.0, 720h (30 days) -> 0.0, log-scaled
        s = _clamp(1 - math.log2(max(mh, 24.0) / 24.0) / math.log2(720.0 / 24.0))
        mh_txt = f"{mh:.0f}h"
    comps["review_speed"] = {
        "raw": mh, "score": s, "weight": WEIGHTS["review_speed"],
        "explanation": f"median PR merge time {mh_txt} (full marks at <=24h, zero at >=30 days)",
    }

    dsp = row.get("days_since_push")
    if dsp is None:
        gaps.append("push date unknown - maintenance is neutral")
        s = 0.5
        dsp_txt = "n/a"
    else:
        dsp = float(dsp)
        s = _clamp(1 - (max(dsp, 7.0) - 7.0) / 173.0)
        dsp_txt = f"{dsp:.0f} days"
    comps["maintenance"] = {
        "raw": dsp, "score": s, "weight": WEIGHTS["maintenance"],
        "explanation": f"last push {dsp_txt} ago (full marks within 7 days, zero after 180)",
    }

    contributors = float(row.get("contributors_count") or 0)
    comps["community"] = {
        "raw": contributors, "score": _clamp(contributors / 5.0), "weight": WEIGHTS["community"],
        "explanation": f"{int(contributors)} contributors (full marks at 5+)",
    }

    rel = float(row.get("releases_count") or 0)
    comps["release_discipline"] = {
        "raw": rel, "score": _clamp(rel / 12.0), "weight": WEIGHTS["release_discipline"],
        "explanation": f"{int(rel)} releases recorded (full marks at 12+)",
    }

    total = sum(c["score"] * c["weight"] for c in comps.values()) * 100
    total = round(total, 1)
    grade = "A" if total >= 85 else "B" if total >= 70 else "C" if total >= 55 else "D" if total >= 40 else "E"
    observed = float(row.get("commits_total") or 0)
    confidence = "high" if observed >= 100 else "medium" if observed >= 20 else "low"
    if confidence == "low":
        gaps.append("fewer than 20 observed commits - treat the score as indicative")
    for c in comps.values():
        c["score"] = round(c["score"], 3)
        c["weight"] = round(c["weight"], 2)
        c["contribution"] = round(c["score"] * c["weight"] * 100, 1)
    weakest = min(comps, key=lambda k: comps[k]["score"])
    return {
        "repo_full_name": row.get("repo_full_name"),
        "score": total,
        "grade": grade,
        "confidence": confidence,
        "components": comps,
        "weakest_component": weakest,
        "data_gaps": gaps,
        "method": "weighted mean of normalised components x 100",
    }
