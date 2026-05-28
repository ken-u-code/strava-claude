"""
Training metrics calculations:
- CTL/ATL/TSB (Fitness, Fatigue, Form)
- Race time predictor (Riegel formula)
- Injury risk assessment (10% rule)
"""

import math
from datetime import datetime, timedelta
from collections import defaultdict


def compute_daily_load(activities: list[dict]) -> dict[str, float]:
    """Compute daily training load (TRIMP) from activity list."""
    daily_load = defaultdict(float)

    for act in activities:
        if act.get("type") not in ("Run", "TrailRun", "VirtualRun"):
            continue

        date_str = act["start_date_local"][:10]
        duration_min = act["moving_time"] / 60
        hr = act.get("average_heartrate")
        max_hr = act.get("max_heartrate") or 190

        if hr and max_hr and hr < max_hr:
            hr_ratio = hr / max_hr
            # Banister TRIMP formula
            trimp = duration_min * hr_ratio * 0.64 * math.exp(1.92 * hr_ratio)
        elif act.get("suffer_score"):
            trimp = act["suffer_score"]
        else:
            # Fallback: distance-based proxy (1 TSS/min at moderate effort)
            trimp = duration_min * 0.7

        daily_load[date_str] += trimp

    return dict(daily_load)


def compute_fitness_freshness(daily_load: dict[str, float]) -> tuple[float, float, float]:
    """
    Returns (CTL, ATL, TSB):
      CTL = Chronic Training Load (fitness)   — 42-day EWA
      ATL = Acute Training Load  (fatigue)    —  7-day EWA
      TSB = Training Stress Balance (form)    = CTL - ATL
    """
    today = datetime.now()
    ctl = 0.0
    atl = 0.0

    for i in range(89, -1, -1):
        date_str = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        load = daily_load.get(date_str, 0.0)
        ctl += (load - ctl) * (1 - math.exp(-1 / 42))
        atl += (load - atl) * (1 - math.exp(-1 / 7))

    tsb = ctl - atl
    return round(ctl, 1), round(atl, 1), round(tsb, 1)


def form_status(tsb: float) -> str:
    if tsb > 10:
        return "Fresh — good time for a quality session or race"
    elif tsb > 0:
        return "Neutral — steady training, manageable fatigue"
    elif tsb > -10:
        return "Slight fatigue — keep efforts easy today"
    else:
        return "Fatigued — prioritise rest or very easy running"


def _fmt_time(seconds: float) -> str:
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def predict_race_times(runs: list[dict]) -> dict:
    """Riegel formula race predictions from the best-paced recent run (≥3 km)."""
    best_run = None
    best_pace = float("inf")

    for run in runs:
        dist = run.get("distance", 0)
        t = run.get("moving_time", 0)
        if dist >= 3000 and t > 0:
            pace = t / (dist / 1000)
            if pace < best_pace:
                best_pace = pace
                best_run = run

    if not best_run:
        return {}

    ref_dist = best_run["distance"]
    ref_time = best_run["moving_time"]

    def riegel(d2_m: float) -> float:
        return ref_time * (d2_m / ref_dist) ** 1.06

    return {
        "5K": _fmt_time(riegel(5000)),
        "10K": _fmt_time(riegel(10000)),
        "Half Marathon": _fmt_time(riegel(21097)),
        "Marathon": _fmt_time(riegel(42195)),
        "based_on": {
            "date": best_run["start_date_local"][:10],
            "distance_km": round(ref_dist / 1000, 2),
            "time": _fmt_time(ref_time),
        },
    }


def check_injury_risk(runs: list[dict]) -> dict:
    """Flag if weekly mileage increased >10% (or >30% = high risk)."""
    now = datetime.now()
    cutoff_7 = now - timedelta(days=7)
    cutoff_14 = now - timedelta(days=14)

    week1 = week2 = 0.0
    for run in runs:
        run_dt = datetime.fromisoformat(run["start_date_local"][:19])
        km = run["distance"] / 1000
        if run_dt >= cutoff_7:
            week1 += km
        elif run_dt >= cutoff_14:
            week2 += km

    change_pct = ((week1 - week2) / week2 * 100) if week2 else 0
    risk = "HIGH ⚠️" if change_pct > 30 else "MODERATE ⚡" if change_pct > 10 else "LOW ✅"

    return {
        "last_7_days_km": round(week1, 1),
        "prev_7_days_km": round(week2, 1),
        "change_pct": round(change_pct, 1),
        "risk_level": risk,
    }


def format_metrics_for_prompt(
    ctl: float,
    atl: float,
    tsb: float,
    race_preds: dict,
    injury: dict,
) -> str:
    lines = [
        "## Calculated Metrics",
        "",
        f"**Fitness & Freshness**",
        f"- Fitness (CTL): {ctl}",
        f"- Fatigue (ATL): {atl}",
        f"- Form (TSB): {tsb} — {form_status(tsb)}",
        "",
        f"**Injury Risk (10% rule)**",
        f"- Last 7 days: {injury['last_7_days_km']} km",
        f"- Prev 7 days: {injury['prev_7_days_km']} km",
        f"- Change: {injury['change_pct']:+.1f}%  |  Risk: {injury['risk_level']}",
    ]

    if race_preds:
        b = race_preds["based_on"]
        lines += [
            "",
            f"**Race Time Predictions** (based on {b['distance_km']} km run on {b['date']} in {b['time']})",
            f"- 5K:            {race_preds['5K']}",
            f"- 10K:           {race_preds['10K']}",
            f"- Half Marathon: {race_preds['Half Marathon']}",
            f"- Marathon:      {race_preds['Marathon']}",
        ]

    return "\n".join(lines)
