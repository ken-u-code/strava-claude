"""
Running MCP server — gives Claude live access to COROS + Strava running data.
COROS provides watch-native metrics (training load, running dynamics, VO2max).
Strava provides social data, gear tracking, and per-km splits.
"""

import os
import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from scripts.strava import (
    fetch_recent_runs,
    fetch_athlete_stats,
    fetch_activity_detail,
    format_runs_for_prompt,
)
from scripts.coros import (
    fetch_coros_activities,
    fetch_coros_activity_detail,
    simplify_coros_activity,
    format_coros_runs_for_prompt,
    coros_activities_to_strava_format,
)
from scripts.metrics import (
    compute_daily_load,
    compute_fitness_freshness,
    form_status,
    predict_race_times,
    check_injury_risk,
)
from scripts.alerts import run_all_alerts, format_alerts_for_report

PROFILE_PATH = Path(__file__).parent / "athlete_profile.md"

PORT = int(os.environ.get("PORT", 8000))

mcp = FastMCP(
    "running-coach",
    instructions=(
        "You have live access to COROS and Strava running data for athlete Kenny Xiao. "
        "Start by reading the athlete-profile resource to understand his goals, "
        "physiology, training rules, and Shanghai marathon plan. "
        "Use COROS tools for watch-native data (training load, running dynamics, "
        "ground contact time, VO2max, running efficiency). Use Strava tools for "
        "social data, per-km splits, and gear tracking. "
        "Always reference his specific benchmarks (Zone 2 pace table, threshold HR "
        "171-174, cadence 180-193 spm) when giving coaching advice."
    ),
    host="0.0.0.0",
    port=PORT,
    stateless_http=True,
)


def _simplify_run(run: dict) -> dict:
    dist_km = run["distance"] / 1000
    pace_sec = run["moving_time"] / dist_km if dist_km else 0
    return {
        "id": run["id"],
        "date": run["start_date_local"][:10],
        "name": run.get("name", "Run"),
        "distance_km": round(dist_km, 2),
        "duration_min": run["moving_time"] // 60,
        "pace_per_km": f"{int(pace_sec // 60)}:{int(pace_sec % 60):02d}",
        "avg_hr": run.get("average_heartrate"),
        "max_hr": run.get("max_heartrate"),
        "elevation_m": run.get("total_elevation_gain", 0),
        "cadence": run.get("average_cadence"),
        "suffer_score": run.get("suffer_score"),
        "workout_type": run.get("workout_type", 0),
        "avg_temp": run.get("average_temp"),
    }


# ── Resources ──

@mcp.resource("running://athlete-profile")
def get_athlete_profile() -> str:
    """Kenny's comprehensive athlete profile: race history, fitness benchmarks,
    physiological profile, training response patterns, shoe rotation rules,
    Shanghai marathon plan, and coaching principles."""
    try:
        return PROFILE_PATH.read_text()
    except FileNotFoundError:
        return "No athlete profile found."


# ── COROS Tools ──

@mcp.tool()
def coros_recent_runs(days: int = 14) -> str:
    """Fetch recent runs from COROS with watch-native metrics.

    Returns COROS-specific data including training load, running efficiency,
    ground contact time, vertical oscillation, stride length, and running
    power — metrics not available from Strava.

    Args:
        days: Number of days to look back (default 14, max 90)
    """
    days = min(max(days, 1), 90)
    try:
        activities = fetch_coros_activities(days, sport_filter="running")
        simplified = [simplify_coros_activity(a) for a in activities]
        total_km = sum(s["distance_km"] for s in simplified)
        return json.dumps({
            "source": "COROS",
            "run_count": len(simplified),
            "total_km": round(total_km, 1),
            "summary": format_coros_runs_for_prompt(activities),
            "runs": simplified,
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to fetch COROS runs: {e}"})


@mcp.tool()
def coros_activity_detail(label_id: str) -> str:
    """Fetch full detail for a single COROS activity.

    Returns detailed lap/split data, HR zones, running dynamics, and
    second-by-second metrics from the COROS watch. Use after coros_recent_runs
    to drill into a specific activity by its label_id.

    Args:
        label_id: The COROS activity label ID (from coros_recent_runs results)
    """
    try:
        detail = fetch_coros_activity_detail(label_id)
        laps = detail.get("lapList", [])
        formatted_laps = []
        for i, lap in enumerate(laps, 1):
            dist_m = lap.get("distance", 0)
            dist_km = dist_m / 100 if dist_m > 10000 else dist_m / 1000
            dur_sec = lap.get("workoutTime", 0) or lap.get("totalTime", 0)
            pace_sec = dur_sec / dist_km if dist_km > 0 else 0
            cadence_raw = lap.get("avgCadence", 0)
            cadence = cadence_raw * 2 if 0 < cadence_raw < 120 else cadence_raw
            formatted_laps.append({
                "lap": i,
                "distance_km": round(dist_km, 2),
                "pace": f"{int(pace_sec // 60)}:{int(pace_sec % 60):02d}" if pace_sec else "—",
                "avg_hr": lap.get("avgHeartRate") or lap.get("avgHr"),
                "max_hr": lap.get("maxHeartRate") or lap.get("maxHr"),
                "cadence_spm": cadence if cadence else None,
                "avg_power_w": lap.get("avgPower"),
                "elevation_gain": lap.get("totalAscent") or lap.get("gainElevation"),
            })

        result = {
            "source": "COROS",
            "label_id": str(detail.get("labelId", label_id)),
            "name": detail.get("name", ""),
            "sport_type": detail.get("sportType"),
            "distance_km": round((detail.get("distance", 0)) / 1000, 2),
            "duration_min": round((detail.get("workoutTime", 0)) / 60, 1),
            "avg_hr": detail.get("avgHeartRate") or detail.get("avgHr"),
            "max_hr": detail.get("maxHeartRate") or detail.get("maxHr"),
            "training_load": detail.get("trainingLoad"),
            "aerobic_effect": detail.get("aerobicEffect"),
            "anaerobic_effect": detail.get("anaerobicEffect"),
            "vo2max": detail.get("estimateVo2max") or detail.get("vo2max"),
            "running_efficiency": detail.get("avgRunningEconomy") or detail.get("avgRunningEfficiency"),
            "avg_ground_contact_ms": detail.get("avgGroundContactTime"),
            "avg_vertical_oscillation_cm": detail.get("avgVerticalOscillation"),
            "avg_stride_length_m": detail.get("avgStrideLength"),
            "avg_power_w": detail.get("avgPower"),
            "calories": detail.get("calorie") or detail.get("totalCalories"),
            "elevation_gain_m": detail.get("totalAscent") or detail.get("gainElevation"),
            "laps": formatted_laps,
        }

        hr_zones = detail.get("heartRateZone") or detail.get("hrZoneList")
        if hr_zones:
            result["hr_zones"] = hr_zones

        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to fetch COROS activity detail: {e}"})


@mcp.tool()
def coros_fitness_metrics(days: int = 90) -> str:
    """Compute fitness/fatigue/form from COROS training history.

    Uses COROS training load values (more accurate than Strava suffer score)
    to calculate CTL/ATL/TSB with exponentially weighted averages.

    Args:
        days: Days of history for calculation (default 90)
    """
    days = min(max(days, 14), 180)
    try:
        activities = fetch_coros_activities(days, sport_filter="running")
        strava_fmt = coros_activities_to_strava_format(activities)
        daily_load = compute_daily_load(strava_fmt)
        ctl, atl, tsb = compute_fitness_freshness(daily_load)
        return json.dumps({
            "source": "COROS",
            "ctl_fitness": ctl,
            "atl_fatigue": atl,
            "tsb_form": tsb,
            "form_status": form_status(tsb),
            "activities_used": len(activities),
            "days_analysed": days,
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to compute COROS fitness metrics: {e}"})


@mcp.tool()
def coros_coaching_alerts(days: int = 14) -> str:
    """Run automated coaching checks against recent COROS activities.

    Checks based on Kenny's personal thresholds: easy run HR (>145),
    training load (280+), VO2 HR (<168), long run pace (<5:00/km),
    cadence (<178), recovery spacing (<4 days), neural floss triggers.

    Args:
        days: Days to check (default 14)
    """
    days = min(max(days, 7), 30)
    try:
        activities = fetch_coros_activities(days, sport_filter="running")
        strava_fmt = coros_activities_to_strava_format(activities)
        alerts = run_all_alerts(strava_fmt)
        return json.dumps({
            "source": "COROS",
            "alert_count": len(alerts),
            "alerts": alerts,
            "formatted": format_alerts_for_report(alerts),
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to run COROS coaching alerts: {e}"})


@mcp.tool()
def coros_race_predictions(days: int = 30) -> str:
    """Predict race times from COROS data using the Riegel formula.

    Finds the best-paced run (>=3km) in the period and extrapolates to
    5K, 10K, Half Marathon, and Marathon distances.

    Args:
        days: Days to search for the reference run (default 30)
    """
    days = min(max(days, 7), 90)
    try:
        activities = fetch_coros_activities(days, sport_filter="running")
        strava_fmt = coros_activities_to_strava_format(activities)
        preds = predict_race_times(strava_fmt)
        if not preds:
            return json.dumps({"error": "No qualifying runs found (need at least one run >=3km)"})
        preds["source"] = "COROS"
        return json.dumps(preds, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to predict race times: {e}"})


@mcp.tool()
def coros_injury_risk() -> str:
    """Check injury risk from COROS data using the 10% weekly mileage rule.

    Compares the last 7 days of running volume against the previous 7 days.
    Flags MODERATE risk if increase >10%, HIGH risk if >30%.
    """
    try:
        activities = fetch_coros_activities(14, sport_filter="running")
        strava_fmt = coros_activities_to_strava_format(activities)
        risk = check_injury_risk(strava_fmt)
        risk["source"] = "COROS"
        return json.dumps(risk, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to check injury risk: {e}"})


# ── Strava Tools ──

@mcp.tool()
def strava_recent_runs(days: int = 14) -> str:
    """Fetch recent running activities from Strava.

    Returns Strava-specific data including per-km splits, gear/shoe info,
    temperature, and suffer score.

    Args:
        days: Number of days to look back (default 14, max 90)
    """
    days = min(max(days, 1), 90)
    try:
        runs = fetch_recent_runs(days)
        return json.dumps({
            "source": "Strava",
            "run_count": len(runs),
            "total_km": round(sum(r["distance"] / 1000 for r in runs), 1),
            "summary": format_runs_for_prompt(runs),
            "runs": [_simplify_run(r) for r in runs],
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to fetch Strava runs: {e}"})


@mcp.tool()
def strava_activity_detail(activity_id: int) -> str:
    """Fetch detailed Strava data for a single activity.

    Returns per-km splits with pace and HR, gear/shoe name, temperature,
    and description. Use after strava_recent_runs to drill into a specific
    activity by its Strava ID.

    Args:
        activity_id: The Strava activity ID (from strava_recent_runs results)
    """
    try:
        detail = fetch_activity_detail(activity_id)
        splits = detail.get("splits_metric", [])
        formatted_splits = []
        for i, s in enumerate(splits, 1):
            pace_sec = s.get("elapsed_time", 0) / (s.get("distance", 1) / 1000)
            formatted_splits.append({
                "km": i,
                "pace": f"{int(pace_sec // 60)}:{int(pace_sec % 60):02d}",
                "avg_hr": s.get("average_heartrate"),
                "elevation_diff": s.get("elevation_difference", 0),
            })
        return json.dumps({
            "source": "Strava",
            "id": detail["id"],
            "name": detail.get("name", ""),
            "date": detail["start_date_local"][:10],
            "distance_km": round(detail["distance"] / 1000, 2),
            "moving_time_min": detail["moving_time"] // 60,
            "avg_hr": detail.get("average_heartrate"),
            "max_hr": detail.get("max_heartrate"),
            "avg_cadence": detail.get("average_cadence"),
            "avg_temp": detail.get("average_temp"),
            "elevation_gain": detail.get("total_elevation_gain", 0),
            "suffer_score": detail.get("suffer_score"),
            "calories": detail.get("calories"),
            "gear": detail.get("gear", {}).get("name") if detail.get("gear") else None,
            "description": detail.get("description", ""),
            "workout_type": detail.get("workout_type", 0),
            "splits_per_km": formatted_splits,
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to fetch Strava activity detail: {e}"})


@mcp.tool()
def strava_athlete_stats() -> str:
    """Fetch year-to-date running statistics from Strava.

    Returns total run count, distance (km), and time (hours) for the
    current year plus all-time totals.
    """
    athlete_id = os.environ.get("STRAVA_ATHLETE_ID", "")
    if not athlete_id:
        return json.dumps({"error": "STRAVA_ATHLETE_ID not configured"})
    try:
        stats = fetch_athlete_stats(athlete_id)
        ytd = stats.get("ytd_run_totals", {})
        all_time = stats.get("all_run_totals", {})
        return json.dumps({
            "source": "Strava",
            "ytd": {
                "runs": ytd.get("count", 0),
                "distance_km": round(ytd.get("distance", 0) / 1000, 1),
                "hours": round(ytd.get("moving_time", 0) / 3600, 1),
                "elevation_m": round(ytd.get("elevation_gain", 0)),
            },
            "all_time": {
                "runs": all_time.get("count", 0),
                "distance_km": round(all_time.get("distance", 0) / 1000, 1),
            },
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to fetch Strava athlete stats: {e}"})


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
