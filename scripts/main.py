"""
Main entry point. Fetches Strava data, analyses with Claude, prints the report.
GitHub Actions captures stdout and creates a GitHub Issue from it.

Usage:
  STRAVA_CLIENT_ID=... STRAVA_CLIENT_SECRET=... STRAVA_REFRESH_TOKEN=... \
  ANTHROPIC_API_KEY=... python scripts/main.py
"""

import os
from datetime import date, datetime

from .strava import fetch_recent_runs, fetch_athlete_stats, format_runs_for_prompt
from .analyze import analyse_runs
from .metrics import (
    compute_daily_load,
    compute_fitness_freshness,
    predict_race_times,
    check_injury_risk,
    format_metrics_for_prompt,
)
from .alerts import run_all_alerts, format_alerts_for_report

PROFILE_PATH = os.path.join(os.path.dirname(__file__), "..", "athlete_profile.md")


def load_athlete_profile() -> str:
    try:
        with open(PROFILE_PATH, "r") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def main():
    print("Loading athlete profile...")
    athlete_profile = load_athlete_profile()
    if athlete_profile:
        print("✅ Athlete profile loaded.")
    else:
        print("⚠️  No athlete_profile.md found — running without personal context.")

    print("Fetching Strava data (90 days for fitness metrics)...")
    all_runs = fetch_recent_runs(days=90)
    recent_runs = [r for r in all_runs if _days_ago(r) <= 14]
    print(f"Found {len(all_runs)} runs (90d) | {len(recent_runs)} in past 14 days.")

    # --- Metrics ---
    daily_load = compute_daily_load(all_runs)
    ctl, atl, tsb = compute_fitness_freshness(daily_load)
    race_preds = predict_race_times(recent_runs or all_runs[:10])
    injury = check_injury_risk(all_runs)
    metrics_summary = format_metrics_for_prompt(ctl, atl, tsb, race_preds, injury)

    # --- Automated alerts ---
    alerts = run_all_alerts(recent_runs)
    alerts_text = format_alerts_for_report(alerts)

    # --- YTD context ---
    athlete_id = os.environ.get("STRAVA_ATHLETE_ID", "")
    ytd_context = ""
    if athlete_id:
        try:
            stats = fetch_athlete_stats(athlete_id)
            ytd = stats.get("ytd_run_totals", {})
            ytd_context = (
                f"Year-to-date: {ytd.get('count', 0)} runs, "
                f"{ytd.get('distance', 0)/1000:.1f} km, "
                f"{ytd.get('moving_time', 0)//3600} hours"
            )
        except Exception:
            pass

    runs_summary = format_runs_for_prompt(recent_runs)

    print("Sending to Claude for analysis...")
    analysis = analyse_runs(
        runs_summary=runs_summary,
        metrics_summary=metrics_summary,
        athlete_profile=athlete_profile,
        ytd_context=ytd_context,
    )

    report = f"""# Running Analysis — {date.today().strftime("%B %d, %Y")}

## 🚨 Automated Alerts
{alerts_text}

{analysis}

---
**Metrics snapshot** | Fitness (CTL): {ctl} | Fatigue (ATL): {atl} | Form (TSB): {tsb:+.1f}
*Generated automatically from Strava data · {len(recent_runs)} activities in past 14 days · Athlete profile v2 loaded*
"""
    print(report)


def _days_ago(run: dict) -> int:
    run_dt = datetime.fromisoformat(run["start_date_local"][:19])
    return (datetime.now() - run_dt).days


if __name__ == "__main__":
    main()
