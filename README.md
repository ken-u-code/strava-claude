# Running Coach MCP — COROS + Strava

MCP server that gives Claude live access to your running data from both COROS (watch-native metrics) and Strava (social, splits, gear).

**Use with Claude Desktop, Claude Code, or any MCP client.**

---

## What it provides

### COROS tools (watch-native data)
- `coros_recent_runs` — training load, running efficiency, ground contact time, VO2max, power
- `coros_activity_detail` — per-lap data with full running dynamics
- `coros_fitness_metrics` — CTL/ATL/TSB computed from COROS training load
- `coros_coaching_alerts` — automated coaching checks against personal thresholds
- `coros_race_predictions` — Riegel formula predictions from best recent effort
- `coros_injury_risk` — 10% weekly mileage increase rule

### Strava tools (social + gear data)
- `strava_recent_runs` — per-km splits, temperature, suffer score
- `strava_activity_detail` — splits with HR, gear/shoe name, description
- `strava_athlete_stats` — year-to-date and all-time totals

### Resource
- `running://athlete-profile` — comprehensive athlete profile with goals, benchmarks, and coaching rules

---

## Setup

### 1. COROS credentials

Use your COROS Training Hub login (same as COROS app):
- Email
- Password
- Region: `us` (Americas/APAC), `eu` (Europe), or `cn` (China)

### 2. Strava API (optional — for splits and gear)

```bash
pip install -r requirements.txt
python scripts/setup_auth.py
```

### 3. Environment variables

```bash
cp .env.example .env
# Fill in COROS_EMAIL, COROS_PASSWORD, COROS_REGION
# Optionally fill in Strava credentials
```

### 4. Run the MCP server

```bash
pip install -r requirements.txt
python mcp_server.py
```

Server starts on port 8000 (or `$PORT`).

### 5. Connect from Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "running-coach": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

---

## Architecture

```
Claude ←→ MCP Server (FastMCP)
              ├── COROS API (training load, dynamics, VO2max)
              ├── Strava API (splits, gear, social)
              ├── Metrics engine (CTL/ATL/TSB, Riegel, injury risk)
              ├── Coaching alerts (9 automated checks)
              └── Athlete profile (goals, benchmarks, rules)
```

---

## Cost

| Component | Cost |
|---|---|
| COROS API | Free (unofficial, reverse-engineered) |
| Strava API | Free (OAuth, rate-limited) |
| MCP server hosting | Free (localhost or Heroku free tier) |
| Claude API (weekly analysis script) | ~$0.01–0.03/run |
| GitHub Actions | Free (public repo) |
