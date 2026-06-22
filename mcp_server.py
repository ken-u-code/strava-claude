"""
Custom Strava MCP server — gives Claude live access to running data.
Wraps the free Strava API with custom coaching metrics and alerts.
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
from scripts.metrics import (
    compute_daily_load,
    compute_fitness_freshness,
    form_status,
    predict_race_times,
    check_injury_risk,
)
from scripts.alerts import run_all_alerts, format_alerts_for_report

PROFILE_PATH = Path(__file__).parent / "athlete_profile.md"

mcp = FastMCP(
    "strava-running",
    instructions=(
        "You have live access to Strava running data for athlete Kenny Xiao. "
        "Start by reading the athlete-profile resource to understand his goals, "
        "physiology, training rules, and Shanghai marathon plan. Then use the data "
        "tools to answer questions from live Strava data. Always reference his "
        "specific benchmarks (Zone 2 pace table, threshold HR 171-174, cadence "
        "180-193 spm) when giving coaching advice."
    ),
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


# --- Resource ---

@mcp.resource("strava://athlete-profile")
def get_athlete_profile() -> str:
    """Kenny's comprehensive athlete profile: race history, fitness benchmarks,
    physiological profile, training response patterns, shoe rotation rules,
    Shanghai marathon plan, and coaching principles."""
    try:
        return PROFILE_PATH.read_text()
    except FileNotFoundError:
        return "No athlete profile found."


# --- Tools ---

@mcp.tool()
def get_recent_runs(days: int = 14) -> str:
    """Fetch recent running activities from Strava.

    Returns a formatted summary plus structured data for each run including
    date, distance, pace, heart rate, elevation, and cadence.

    Args:
        days: Number of days to look back (default 14, max 90)
    """
    days = min(max(days, 1), 90)
    try:
        runs = fetch_recent_runs(days)
        return json.dumps({
            "run_count": len(runs),
            "total_km": round(sum(r["distance"] / 1000 for r in runs), 1),
            "summary": format_runs_for_prompt(runs),
            "runs": [_simplify_run(r) for r in runs],
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to fetch runs: {e}"})


@mcp.tool()
def get_activity_detail(activity_id: int) -> str:
    """Fetch detailed data for a single Strava activity.

    Returns comprehensive data including splits, heart rate zones, cadence,
    temperature, gear, and suffer score. Use after get_recent_runs to drill
    into a specific activity by its ID.

    Args:
        activity_id: The Strava activity ID (from get_recent_runs results)
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
        return json.dumps({"error": f"Failed to fetch activity detail: {e}"})


@mcp.tool()
def get_fitness_metrics(days: int = 90) -> str:
    """Compute fitness, fatigue, and form (CTL/ATL/TSB) from training history.

    Uses exponentially weighted averages:
    - CTL (Chronic Training Load) = fitness, 42-day average
    - ATL (Acute Training Load) = fatigue, 7-day average
    - TSB (Training Stress Balance) = form = CTL - ATL

    Positive TSB means fresh, negative means fatigued.

    Args:
        days: Days of history for calculation (default 90)
    """
    days = min(max(days, 14), 180)
    try:
        runs = fetch_recent_runs(days)
        daily_load = compute_daily_load(runs)
        ctl, atl, tsb = compute_fitness_freshness(daily_load)
        return json.dumps({
            "ctl_fitness": ctl,
            "atl_fatigue": atl,
            "tsb_form": tsb,
            "form_status": form_status(tsb),
            "activities_used": len(runs),
            "days_analysed": days,
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to compute fitness metrics: {e}"})


@mcp.tool()
def get_race_predictions(days: int = 30) -> str:
    """Predict race times using the Riegel formula based on recent training.

    Finds the best-paced run (>=3km) in the period and extrapolates to
    5K, 10K, Half Marathon, and Marathon distances.

    Args:
        days: Days to search for the reference run (default 30)
    """
    days = min(max(days, 7), 90)
    try:
        runs = fetch_recent_runs(days)
        preds = predict_race_times(runs)
        if not preds:
            return json.dumps({"error": "No qualifying runs found (need at least one run >=3km)"})
        return json.dumps(preds, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to predict race times: {e}"})


@mcp.tool()
def get_injury_risk() -> str:
    """Check injury risk based on the 10% weekly mileage increase rule.

    Compares the last 7 days of running volume against the previous 7 days.
    Flags MODERATE risk if increase >10%, HIGH risk if >30%.
    """
    try:
        runs = fetch_recent_runs(days=14)
        risk = check_injury_risk(runs)
        return json.dumps(risk, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to check injury risk: {e}"})


@mcp.tool()
def get_coaching_alerts(days: int = 14) -> str:
    """Run all 9 automated coaching checks against recent activities.

    Checks: easy run HR (>145), training load (280+), VO2 HR (<168),
    long run pace (<5:00/km), cadence (<178), heat adjustment (>22C),
    carbon plate distance, recovery spacing (<4 days), neural floss triggers.

    Based on Kenny's personal thresholds from his athlete profile.

    Args:
        days: Days to check (default 14)
    """
    days = min(max(days, 7), 30)
    try:
        runs = fetch_recent_runs(days)
        alerts = run_all_alerts(runs)
        return json.dumps({
            "alert_count": len(alerts),
            "alerts": alerts,
            "formatted": format_alerts_for_report(alerts),
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to run coaching alerts: {e}"})


@mcp.tool()
def get_athlete_stats() -> str:
    """Fetch year-to-date running statistics from Strava.

    Returns total run count, distance (km), and time (hours) for the
    current year.
    """
    athlete_id = os.environ.get("STRAVA_ATHLETE_ID", "")
    if not athlete_id:
        return json.dumps({"error": "STRAVA_ATHLETE_ID not configured"})
    try:
        stats = fetch_athlete_stats(athlete_id)
        ytd = stats.get("ytd_run_totals", {})
        all_time = stats.get("all_run_totals", {})
        return json.dumps({
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
        return json.dumps({"error": f"Failed to fetch athlete stats: {e}"})


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
