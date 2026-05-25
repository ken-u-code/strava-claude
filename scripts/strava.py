"""Strava API client — handles token refresh and data fetching."""

import os
import time
import requests

STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"


def get_access_token() -> str:
    resp = requests.post(
        STRAVA_TOKEN_URL,
        data={
            "client_id": os.environ["STRAVA_CLIENT_ID"],
            "client_secret": os.environ["STRAVA_CLIENT_SECRET"],
            "refresh_token": os.environ["STRAVA_REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _get(path: str, token: str, params: dict = None) -> dict | list:
    resp = requests.get(
        f"{STRAVA_API_BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
        params=params or {},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_recent_runs(days: int = 14) -> list[dict]:
    """Return run activities from the past `days` days."""
    token = get_access_token()
    after = int(time.time()) - days * 86400
    activities = _get("/athlete/activities", token, {"per_page": 50, "after": after})
    runs = [a for a in activities if a["type"] in ("Run", "TrailRun", "VirtualRun")]
    return runs


def fetch_athlete_stats(athlete_id: str) -> dict:
    token = get_access_token()
    return _get(f"/athletes/{athlete_id}/stats", token)


def fetch_activity_detail(activity_id: int) -> dict:
    token = get_access_token()
    return _get(f"/activities/{activity_id}", token)


def format_runs_for_prompt(runs: list[dict]) -> str:
    """Convert raw Strava activity list into a compact readable summary."""
    if not runs:
        return "No runs in this period."

    lines = []
    for r in runs:
        dist_km = r["distance"] / 1000
        duration_min = r["moving_time"] // 60
        pace_sec = r["moving_time"] / (r["distance"] / 1000) if r["distance"] else 0
        pace_min = int(pace_sec // 60)
        pace_s = int(pace_sec % 60)
        hr = r.get("average_heartrate")
        elev = r.get("total_elevation_gain", 0)
        date = r["start_date_local"][:10]
        name = r.get("name", "Run")
        hr_str = f", avg HR {hr:.0f} bpm" if hr else ""
        lines.append(
            f"- {date} | {name} | {dist_km:.2f} km in {duration_min} min "
            f"(pace {pace_min}:{pace_s:02d}/km{hr_str}, elev +{elev:.0f}m)"
        )
    return "\n".join(lines)
