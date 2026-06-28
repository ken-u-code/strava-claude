"""COROS Training Hub API client — fetches running data with watch-specific metrics."""

import os
import time
import hashlib
import logging
from datetime import datetime, timedelta

import bcrypt
import requests

logger = logging.getLogger(__name__)

_REGION_URLS = {
    "us": "https://teamapi.coros.com",
    "eu": "https://teameuapi.coros.com",
    "cn": "https://teamcnapi.coros.com",
}

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://training.coros.com",
    "Referer": "https://training.coros.com/",
    "Content-Type": "application/json",
}

SPORT_TYPE_RUNNING = {100, 101, 102, 103}

_token_cache: dict = {}


def _base_url() -> str:
    region = os.environ.get("COROS_REGION", "us").lower()
    return _REGION_URLS.get(region, _REGION_URLS["us"])


def _authenticate() -> tuple[str, str]:
    """Login to COROS and return (access_token, user_id). Caches for 20 min."""
    cached = _token_cache.get("auth")
    if cached and cached["expires"] > time.time():
        return cached["token"], cached["user_id"]

    email = os.environ["COROS_EMAIL"]
    password = os.environ["COROS_PASSWORD"]

    password_md5 = hashlib.md5(password.encode("utf-8")).hexdigest()
    salt = bcrypt.gensalt(rounds=10)
    hashed = bcrypt.hashpw(password_md5.encode("utf-8"), salt)

    payload = {
        "account": email,
        "accountType": 2,
        "p1": hashed.decode("utf-8"),
        "p2": salt.decode("utf-8"),
    }

    resp = requests.post(
        f"{_base_url()}/account/login",
        json=payload,
        headers=BROWSER_HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("result") != "0000":
        raise RuntimeError(f"COROS login failed: {data.get('message', 'unknown error')}")

    token = data["data"]["accessToken"]
    user_id = str(data["data"]["userId"])

    _token_cache["auth"] = {
        "token": token,
        "user_id": user_id,
        "expires": time.time() + 1200,
    }
    return token, user_id


def _api_headers(token: str, user_id: str) -> dict:
    return {
        **BROWSER_HEADERS,
        "accesstoken": token,
        "yfheader": f'{{"userId":"{user_id}"}}',
    }


def _get(path: str, params: dict | None = None) -> dict:
    token, user_id = _authenticate()
    resp = requests.get(
        f"{_base_url()}{path}",
        params=params or {},
        headers=_api_headers(token, user_id),
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("result") != "0000":
        raise RuntimeError(f"COROS API error: {data.get('message', 'unknown')}")
    return data.get("data", {})


def fetch_coros_activities(days: int = 14, sport_filter: str = "running") -> list[dict]:
    """Fetch activities from COROS Training Hub.

    Returns raw activity dicts with all available fields.
    """
    mode_list = ""
    if sport_filter == "running":
        mode_list = "100"

    data = _get("/activity/query", {
        "size": 200,
        "pageNumber": 1,
        "modeList": mode_list,
    })

    cutoff = time.time() - days * 86400
    activities = []

    for act in data.get("dataList", []):
        start = act.get("startTime", 0)
        if start < cutoff:
            continue
        if sport_filter == "running" and act.get("sportType", 0) not in SPORT_TYPE_RUNNING:
            continue
        activities.append(act)

    activities.sort(key=lambda a: a.get("startTime", 0), reverse=True)
    return activities


def fetch_coros_activity_detail(label_id: str) -> dict:
    """Fetch detailed data for a single COROS activity."""
    return _get("/activity/detail/query", {"labelId": label_id})


def simplify_coros_activity(act: dict) -> dict:
    """Convert raw COROS activity to a clean summary dict."""
    dist_m = act.get("distance", 0)
    dist_km = dist_m / 100 if dist_m > 100000 else dist_m / 1000
    # COROS distance can be in cm or m depending on version — normalize
    if dist_km > 500:
        dist_km = dist_m / 100000

    workout_sec = act.get("workoutTime", 0)
    pace_sec = workout_sec / dist_km if dist_km > 0 else 0

    start_ts = act.get("startTime", 0)
    date_str = datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d") if start_ts else ""
    time_str = datetime.fromtimestamp(start_ts).strftime("%H:%M") if start_ts else ""

    cadence_raw = act.get("avgCadence", 0)
    cadence = cadence_raw * 2 if 0 < cadence_raw < 120 else cadence_raw

    return {
        "label_id": str(act.get("labelId", "")),
        "date": date_str,
        "time": time_str,
        "name": act.get("name", "Run"),
        "sport_type": act.get("sportType", 0),
        "distance_km": round(dist_km, 2),
        "duration_min": round(workout_sec / 60, 1),
        "pace_per_km": f"{int(pace_sec // 60)}:{int(pace_sec % 60):02d}" if pace_sec else "—",
        "avg_hr": act.get("avgHeartRate") or act.get("avgHr"),
        "max_hr": act.get("maxHeartRate") or act.get("maxHr"),
        "cadence_spm": cadence if cadence else None,
        "calories": act.get("calorie") or act.get("totalCalories"),
        "elevation_gain_m": act.get("totalAscent") or act.get("gainElevation"),
        "elevation_loss_m": act.get("totalDescent") or act.get("lossElevation"),
        "training_load": act.get("trainingLoad"),
        "aerobic_effect": _scale_10(act.get("aerobicEffect")),
        "anaerobic_effect": _scale_10(act.get("anaerobicEffect")),
        "avg_stride_length_m": _cm_to_m(act.get("avgStrideLength")),
        "avg_ground_contact_ms": act.get("avgGroundContactTime") or act.get("avgGctBalance"),
        "avg_vertical_oscillation_cm": _mm_to_cm(act.get("avgVerticalOscillation")),
        "avg_vertical_ratio_pct": _scale_10(act.get("avgVerticalRatio")),
        "running_efficiency": act.get("avgRunningEconomy") or act.get("avgRunningEfficiency"),
        "avg_power_w": act.get("avgPower"),
        "vo2max": act.get("estimateVo2max") or act.get("vo2max"),
    }


def _scale_10(val) -> float | None:
    """COROS stores some values ×10 (e.g. aerobic effect 35 = 3.5)."""
    if val and val > 10:
        return round(val / 10, 1)
    return val


def _cm_to_m(val) -> float | None:
    if val and val > 10:
        return round(val / 100, 2)
    return val


def _mm_to_cm(val) -> float | None:
    if val and val > 100:
        return round(val / 10, 1)
    return val


def format_coros_runs_for_prompt(activities: list[dict]) -> str:
    """Format raw COROS activities into a readable summary."""
    if not activities:
        return "No runs found in this period."

    lines = []
    for act in activities:
        s = simplify_coros_activity(act)
        hr_str = f", avg HR {s['avg_hr']} bpm" if s["avg_hr"] else ""
        load_str = f", load {s['training_load']}" if s["training_load"] else ""
        cadence_str = f", {s['cadence_spm']} spm" if s["cadence_spm"] else ""
        elev_str = f", +{s['elevation_gain_m']}m" if s["elevation_gain_m"] else ""
        lines.append(
            f"- {s['date']} {s['time']} | {s['name']} | "
            f"{s['distance_km']} km in {s['duration_min']} min "
            f"({s['pace_per_km']}/km{hr_str}{cadence_str}{load_str}{elev_str})"
        )
    return "\n".join(lines)


def coros_activities_to_strava_format(activities: list[dict]) -> list[dict]:
    """Convert COROS activities to Strava-like dicts for the metrics/alerts modules."""
    converted = []
    for act in activities:
        dist_m = act.get("distance", 0)
        if dist_m > 100000:
            dist_m = dist_m / 100

        cadence_raw = act.get("avgCadence", 0)
        cadence = cadence_raw * 2 if 0 < cadence_raw < 120 else cadence_raw

        start_ts = act.get("startTime", 0)
        dt = datetime.fromtimestamp(start_ts)

        workout_type = 0
        name = (act.get("name") or "").lower()
        if any(w in name for w in ["race", "parkrun", "event"]):
            workout_type = 1
        elif any(w in name for w in ["long run", "long"]):
            workout_type = 2
        elif any(w in name for w in ["tempo", "interval", "vo2", "threshold", "workout", "rep"]):
            workout_type = 3

        converted.append({
            "id": act.get("labelId"),
            "type": "Run",
            "start_date_local": dt.isoformat(),
            "distance": dist_m,
            "moving_time": act.get("workoutTime", 0),
            "average_heartrate": act.get("avgHeartRate") or act.get("avgHr"),
            "max_heartrate": act.get("maxHeartRate") or act.get("maxHr"),
            "total_elevation_gain": act.get("totalAscent") or act.get("gainElevation") or 0,
            "average_cadence": cadence if cadence else None,
            "suffer_score": act.get("trainingLoad"),
            "workout_type": workout_type,
            "average_temp": None,
            "name": act.get("name", "Run"),
        })
    return converted
