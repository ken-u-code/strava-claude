"""Send run data to Claude and return a structured analysis."""

import os
import anthropic

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """You are an expert running coach and sports scientist.
Analyse the athlete's recent training data and provide concise, actionable advice.
Return your response as structured markdown with these exact sections:

## Training Summary
A 2-3 sentence overview of the week's volume, intensity, and consistency.

## Key Observations
3-5 bullet points on patterns, load distribution, and notable efforts.

## Personal Records
List any new PRs detected (fastest pace, longest run, etc.) compared to the data provided.
If no PRs, write "No new PRs this period."

## Training Advice
3-5 prioritised recommendations for the next 7-14 days. Be specific (paces, durations).

## Content Draft
A short Strava post caption (2-3 sentences, motivational but honest) for the most notable run.
"""


def analyse_runs(runs_summary: str, athlete_context: str = "") -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    user_message = f"""Here is the athlete's running data for the past 14 days:

{runs_summary}

{f"Additional context: {athlete_context}" if athlete_context else ""}

Please provide your full analysis."""

    response = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    return response.content[0].text
