"""Send run data to Claude and return a structured analysis."""

import os
import anthropic

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """You are an expert running coach and sports scientist.
Analyse the athlete's recent training data and pre-calculated metrics, then provide
concise, actionable advice. Return your response as structured markdown with these
exact sections — do not add or remove sections:

## Training Summary
2-3 sentences covering volume, intensity distribution, and consistency over the past 14 days.

## Fitness & Freshness
Interpret the CTL/ATL/TSB values provided. Explain what the numbers mean for this athlete
right now in plain English. Is this a good week to push hard or back off?

## Race Time Predictions
Present the predicted times in a clean table. Comment on whether these look realistic
given the recent training and add one sentence of context (e.g. "with consistent training
you could target X by Y").

## Key Observations
3-5 bullet points on patterns: pace trends, effort distribution, notable runs, consistency.

## Personal Records
List any new PRs detected (fastest pace, longest run, best effort per distance).
If no PRs this period, write "No new PRs this period — keep building."

## Injury Risk
Interpret the 10% rule result. If risk is MODERATE or HIGH, give specific advice on
how to reduce load this week. If LOW, confirm it's safe to continue as planned.

## This Week's Recommended Session
Suggest ONE specific quality workout for the coming week based on current form (TSB).
Include: session type, warm-up, main set with target pace or effort, cool-down.
Keep it to 6-8 lines.

## Strava Caption
A punchy 2-3 sentence caption for the most notable run this period.
Include 3-5 relevant hashtags on the last line.
"""


def analyse_runs(
    runs_summary: str,
    metrics_summary: str = "",
    athlete_profile: str = "",
    ytd_context: str = "",
) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    profile_block = (
        f"<athlete_profile>\n{athlete_profile}\n</athlete_profile>\n"
        if athlete_profile
        else ""
    )

    user_message = f"""{profile_block}
Here is the athlete's running data for the past 14 days:

{runs_summary}

{metrics_summary}

{f"Year-to-date context: {ytd_context}" if ytd_context else ""}

Using the athlete profile above for full context on this athlete's history, goals, physiology, and coaching rules, please provide your full analysis. Reference specific data points from their profile where relevant (e.g. compare current Zone 2 pace to their benchmark table, flag if session type is on their confirmed ineffective list, reference Shanghai sub-3 decision gates)."""

    response = client.messages.create(
        model=MODEL,
        max_tokens=2500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    return response.content[0].text
