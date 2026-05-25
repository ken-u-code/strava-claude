"""
Main entry point. Fetches Strava data, analyses with Claude, prints the report.
GitHub Actions captures stdout and creates a GitHub Issue from it.

Usage:
  STRAVA_CLIENT_ID=... STRAVA_CLIENT_SECRET=... STRAVA_REFRESH_TOKEN=... \
  ANTHROPIC_API_KEY=... python scripts/main.py
"""

import os
import sys
from datetime import date

from strava import fetch_recent_runs, fetch_athlete_stats, format_runs_for_prompt
from analyze import analyse_runs


def main():
    print(f"Fetching Strava data...")
    runs = fetch_recent_runs(days=14)
    print(f"Found {len(runs)} runs in the past 14 days.")

    athlete_id = os.environ.get("STRAVA_ATHLETE_ID", "")
    stats_context = ""
    if athlete_id:
        try:
            stats = fetch_athlete_stats(athlete_id)
            ytd = stats.get("ytd_run_totals", {})
            stats_context = (
                f"Year-to-date: {ytd.get('count', 0)} runs, "
                f"{ytd.get('distance', 0)/1000:.1f} km, "
                f"{ytd.get('moving_time', 0)//3600} hours"
            )
        except Exception:
            pass  # stats are bonus context, not critical

    runs_summary = format_runs_for_prompt(runs)

    print("Sending to Claude for analysis...")
    analysis = analyse_runs(runs_summary, stats_context)

    # Output the full report — GitHub Actions captures this
    report = f"""# Running Analysis — {date.today().strftime("%B %d, %Y")}

{analysis}

---
*Generated automatically from Strava data. {len(runs)} activities analysed.*
"""
    print(report)


if __name__ == "__main__":
    main()
