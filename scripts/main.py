"""
Main entry point. Fetches Strava data, analyses with Claude, prints the report.
GitHub Actions captures stdout and creates a GitHub Issue from it.

Usage:
  STRAVA_CLIENT_ID=... STRAVA_CLIENT_SECRET=... STRAVA_REFRESH_TOKEN=... \
  ANTHROPIC_API_KEY=... python scripts/main.py
"""

import os
from datetime import date

from strava import fetch_recent_runs, fetch_athlete_stats, format_runs_for_prompt
from analyze import analyse_runs
from metrics import (
    compute_daily_load,
    compute_fitness_freshness,
    predict_race_times,
    check_injury_risk,
    format_metrics_for_prompt,
)


def main():
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

    # --- Athlete context ---
    athlete_id = os.environ.get("STRAVA_ATHLETE_ID", "")
    athlete_context = ""
    if athlete_id:
        try:
            from strava import fetch_athlete_stats
            stats = fetch_athlete_stats(athlete_id)
            ytd = stats.get("ytd_run_totals", {})
            athlete_context = (
                f"Year-to-date: {ytd.get('count', 0)} runs, "
                f"{ytd.get('distance', 0)/1000:.1f} km, "
                f"{ytd.get('moving_time', 0)//3600} hours"
            )
        except Exception:
            pass

    runs_summary = format_runs_for_prompt(recent_runs)

    print("Sending to Claude for analysis...")
    analysis = analyse_runs(runs_summary, metrics_summary, athlete_context)

    report = f"""# Running Analysis — {date.today().strftime("%B %d, %Y")}

{analysis}

---
**Metrics snapshot** | Fitness (CTL): {ctl} | Fatigue (ATL): {atl} | Form (TSB): {tsb:+.1f}
*Generated automatically from Strava data. {len(recent_runs)} activities in past 14 days analysed.*
"""
    print(report)


def _days_ago(run: dict) -> int:
    from datetime import datetime
    run_dt = datetime.fromisoformat(run["start_date_local"][:19])
    return (datetime.now() - run_dt).days


if __name__ == "__main__":
    main()
