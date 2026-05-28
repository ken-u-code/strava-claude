"""
Automated coaching alerts based on Kenny's profile (Section 13).
Each check returns a dict with: triggered (bool), level, message.
"""

from datetime import datetime, timedelta


def check_easy_run_hr(run: dict) -> dict | None:
    """Easy run HR > 145 bpm = too hard."""
    workout_type = run.get("workout_type", 0)
    avg_hr = run.get("average_heartrate")
    # workout_type 0 = default run, 1 = race, 2 = long run, 3 = workout
    if workout_type not in (0, 2):
        return None
    if avg_hr and avg_hr > 145:
        temp = run.get("average_temp")
        temp_note = f" (temp: {temp:.0f}°C — heat likely culprit)" if temp and temp > 22 else ""
        return {
            "level": "⚠️ WARNING",
            "message": f"Easy run HR was {avg_hr:.0f} bpm — above 145 target{temp_note}. Check fatigue levels and temperature.",
        }
    return None


def check_training_load(run: dict) -> dict | None:
    """Training Load HIGH 280+ = mandatory rest next day."""
    load = run.get("suffer_score")
    if load and load >= 280:
        return {
            "level": "🔴 MANDATORY REST",
            "message": f"Training Load {load:.0f} — above 280 threshold. Full rest tomorrow. No exceptions per your protocol.",
        }
    return None


def check_vo2_hr(run: dict) -> dict | None:
    """VO2 session HR < 168 bpm = reps not hard enough."""
    workout_type = run.get("workout_type", 0)
    avg_hr = run.get("average_heartrate")
    name = run.get("name", "").lower()
    is_vo2 = workout_type == 3 or any(w in name for w in ["vo2", "interval", "800m", "1.6km", "rep"])
    if is_vo2 and avg_hr and avg_hr < 168:
        return {
            "level": "⚡ NOTE",
            "message": f"VO2 session avg HR {avg_hr:.0f} bpm — below 168 target zone. Push harder on reps next session.",
        }
    return None


def check_long_run_pace(run: dict) -> dict | None:
    """Long run pace < 5:00/km without MP structure = drifting too fast."""
    workout_type = run.get("workout_type", 0)
    dist = run.get("distance", 0)
    time = run.get("moving_time", 0)
    if workout_type != 2 and dist < 15000:
        return None
    if time == 0:
        return None
    pace_sec_km = time / (dist / 1000)
    if pace_sec_km < 300:  # faster than 5:00/km
        return {
            "level": "⚠️ CHECK",
            "message": f"Long run avg pace {int(pace_sec_km//60)}:{int(pace_sec_km%60):02d}/km — below 5:00/km. Was this intentional MP structure? If not, you may be accumulating fatigue.",
        }
    return None


def check_cadence(run: dict) -> dict | None:
    """Cadence < 178 spm = form check."""
    cadence = run.get("average_cadence")
    if cadence and cadence < 178:
        return {
            "level": "⚡ FORM",
            "message": f"Cadence {cadence:.0f} spm — below your 180–193 target. Focus on quick light steps.",
        }
    return None


def check_heat_adjustment(run: dict) -> dict | None:
    """Temp > 22°C for quality session = pace adjustment needed."""
    temp = run.get("average_temp")
    workout_type = run.get("workout_type", 0)
    if workout_type in (1, 3) and temp and temp > 22:
        return {
            "level": "🌡️ HEAT",
            "message": f"Quality session in {temp:.0f}°C — add 5–8 sec/km to pace targets. HR data more reliable than pace today.",
        }
    return None


def check_carbon_plate_distance(run: dict) -> dict | None:
    """Alphafly on runs > 25km = warning."""
    gear = run.get("gear_id", "")
    dist = run.get("distance", 0)
    name = run.get("name", "").lower()
    is_alphafly = "alphafly" in name  # best we can do without gear name lookup
    if is_alphafly and dist > 25000:
        return {
            "level": "👟 SHOE",
            "message": f"Alphafly on a {dist/1000:.1f}km run — switch to Megablast for long runs to preserve carbon plate and protect legs.",
        }
    return None


def check_recovery_between_hard_sessions(runs: list[dict]) -> dict | None:
    """Two hard sessions within 4 days = recovery warning."""
    hard_sessions = []
    for run in runs:
        wt = run.get("workout_type", 0)
        if wt in (1, 3):  # race or workout
            dt = datetime.fromisoformat(run["start_date_local"][:19])
            hard_sessions.append(dt)

    hard_sessions.sort()
    for i in range(1, len(hard_sessions)):
        gap = (hard_sessions[i] - hard_sessions[i - 1]).days
        if gap < 4:
            return {
                "level": "🔴 RECOVERY",
                "message": f"Two hard sessions only {gap} days apart — your protocol requires minimum 4 days between quality sessions.",
            }
    return None


def check_neural_floss_reminder(run: dict) -> dict | None:
    """Calf/hamstring mentioned = neural floss reminder."""
    desc = (run.get("description") or "").lower()
    name = (run.get("name") or "").lower()
    keywords = ["calf", "hamstring", "tight", "nerve", "tibial"]
    if any(kw in desc or kw in name for kw in keywords):
        return {
            "level": "🧠 INJURY PREVENTION",
            "message": "Calf/hamstring flagged in session — neural floss tonight: 2 sets × 8–10 reps. Gentle, never into pain.",
        }
    return None


def run_all_alerts(runs: list[dict]) -> list[str]:
    """Run all alert checks and return formatted alert strings."""
    alerts = []

    # Per-run checks on most recent run
    if runs:
        latest = runs[0]
        checks = [
            check_easy_run_hr(latest),
            check_training_load(latest),
            check_vo2_hr(latest),
            check_long_run_pace(latest),
            check_cadence(latest),
            check_heat_adjustment(latest),
            check_carbon_plate_distance(latest),
            check_neural_floss_reminder(latest),
        ]
        for check in checks:
            if check:
                alerts.append(f"**{check['level']}** — {check['message']}")

    # Cross-run checks
    recovery_check = check_recovery_between_hard_sessions(runs)
    if recovery_check:
        alerts.append(f"**{recovery_check['level']}** — {recovery_check['message']}")

    return alerts


def format_alerts_for_report(alerts: list[str]) -> str:
    if not alerts:
        return "✅ No automated alerts triggered this period."
    return "\n".join(f"- {a}" for a in alerts)
