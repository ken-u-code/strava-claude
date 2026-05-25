# Strava × Claude — Running Analysis

Automatically fetches your Strava runs, analyses them with Claude, and posts a weekly report as a GitHub Issue (which emails you).

**Runs on GitHub Actions — free, no server needed.**

---

## What it produces each week

- **Training summary** — volume, intensity, consistency
- **Key observations** — patterns and notable efforts
- **PR detection** — new personal records
- **Training advice** — specific recommendations for the next 2 weeks
- **Content draft** — ready-to-post Strava caption for your best run

---

## Setup (one time, ~15 minutes)

### 1. Create a Strava API app

1. Go to [strava.com/settings/api](https://www.strava.com/settings/api)
2. Create an app — name it anything (e.g. "My Running Dashboard")
3. Set **Authorization Callback Domain** to `localhost`
4. Copy your **Client ID** and **Client Secret**

### 2. Get your Strava refresh token

```bash
pip install requests
python scripts/setup_auth.py
```

A browser window opens, you authorise the app, and the script prints your four secrets.

### 3. Get an Anthropic API key

1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Sign up → **API Keys** → **Create Key**
3. New accounts receive free trial credits (~$5)
4. Cost per weekly run: ~$0.02

### 4. Create a GitHub repository

```bash
cd strava-claude
git init
git add .
git commit -m "Initial commit"
gh repo create strava-claude --public --push --source=.
```

> Public repos get **unlimited** free GitHub Actions minutes.

### 5. Add secrets to GitHub

In your repo: **Settings → Secrets and variables → Actions → New repository secret**

Add all five secrets printed by `setup_auth.py`:

| Secret name | Value |
|---|---|
| `STRAVA_CLIENT_ID` | From step 1 |
| `STRAVA_CLIENT_SECRET` | From step 1 |
| `STRAVA_REFRESH_TOKEN` | From step 2 |
| `STRAVA_ATHLETE_ID` | From step 2 |
| `ANTHROPIC_API_KEY` | From step 3 |

### 6. Create the `running-analysis` label

In your repo: **Issues → Labels → New label** → name it `running-analysis`

### 7. Test it manually

Go to **Actions → Weekly Running Analysis → Run workflow** → click **Run workflow**.

Check the Issues tab after ~30 seconds — your first report will appear there, and GitHub will email you.

---

## Schedule

The workflow runs every **Monday at 7:00 AM UTC** by default.

To change the schedule, edit the `cron` line in [`.github/workflows/strava_analysis.yml`](.github/workflows/strava_analysis.yml):

```yaml
- cron: "0 7 * * 1"   # Mon 7am UTC
# Examples:
# "0 6 * * *"          # Daily 6am UTC
# "0 8 * * 3,6"        # Wed + Sat 8am UTC
```

---

## Local testing

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in your secrets
cd scripts
source ../.env && python main.py
```

---

## Cost

| Component | Cost |
|---|---|
| GitHub Actions | Free (public repo = unlimited) |
| Strava API | Free |
| Claude API (per run) | ~$0.01–0.03 |
