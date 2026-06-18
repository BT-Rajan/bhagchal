"""
Player behavioral analysis service.

Internally this calls the DeepSeek API to do the actual inference, but
every user-facing string (the report, the email, error messages a player
or admin might see) is branded only as Config.COGZI_MODEL_NAME. The model
itself is instructed to never reveal it is DeepSeek (or any other vendor).

Returns structured data (a dict of distinct fields) rather than a single
free-text blob. This is what was actually causing the "truncated in the
middle" report: a single long free-text completion has no natural recovery
point if it's cut off near the token limit. Structured JSON either parses
completely or fails cleanly -- it can't render as a sentence trailing off
mid-thought -- and it lets the PDF builder lay out clean, consistent
sections instead of depending on the model to format its own prose.
"""
import json
import re

import requests

from config import Config


class AnalysisError(Exception):
    """Raised when a report can't be analyzed (missing data, malformed response, API failure, etc.)."""


# Fields the model must return, and a short description of each used both
# in the prompt and to validate the parsed response.
_REQUIRED_FIELDS = {
    'traits': 'array of 3-5 short trait keywords (e.g. "Patient", "Risk-averse")',
    'decision_style': '2-4 sentence narrative on decision-making style',
    'strengths': 'array of 2-4 short strategic strengths',
    'weaknesses': 'array of 2-4 short strategic weaknesses',
    'temperament': '2-4 sentence narrative on emotional/temperamental traits',
    'adaptability': '2-4 sentence narrative on pattern recognition and adaptability',
    'overall_assessment': '3-5 sentence concluding assessment with suggestions for improvement',
    'match_percentage': 'integer 0-100, estimated behavioral fit against the job description expectations',
}


def summarize_player_stats(report):
    """
    Extract and compute human-specific statistics from the report.
    Assumes the human role is given in report['human_role'].
    Returns (stats, human_moves), or (None, None) if human_role is missing.
    """
    human_role = report.get('human_role')  # 'tiger' or 'goat'
    if not human_role:
        return None, None

    # Filter moves by the human's faction
    human_moves = [m for m in report['move_log'] if m['faction'] == human_role]
    ai_moves = [m for m in report['move_log'] if m['faction'] != human_role]

    # Basic stats
    total_human_moves = len(human_moves)
    total_ai_moves = len(ai_moves)
    human_captures = sum(1 for m in human_moves if m.get('is_capture', False))
    ai_captures = sum(1 for m in ai_moves if m.get('is_capture', False))

    # Timing stats (time_since_prev is already in the report)
    human_times = [m.get('time_since_prev', 0) for m in human_moves if m.get('time_since_prev', 0) > 0]
    avg_human_time = round(sum(human_times) / len(human_times), 2) if human_times else 0
    max_human_time = round(max(human_times), 2) if human_times else 0
    min_human_time = round(min(human_times), 2) if human_times else 0

    # Legal moves considered (average number of legal moves available)
    legal_moves_counts = [len(m.get('legal_moves', [])) for m in human_moves]
    avg_legal_moves = round(sum(legal_moves_counts) / len(legal_moves_counts), 1) if legal_moves_counts else 0

    # Captures attempted (human moves that had a capture as an option but didn't take)
    # We can infer from 'legal_moves' containing strings with '✕' (capture symbol)
    capture_opportunities = 0
    for m in human_moves:
        if any('✕' in lm for lm in m.get('legal_moves', [])):
            capture_opportunities += 1
    captures_taken = human_captures
    capture_conversion_rate = round(captures_taken / capture_opportunities * 100, 1) if capture_opportunities > 0 else 0

    # Outcome
    result = report.get('status')
    human_won = (human_role == 'tiger' and result == 'tiger_win') or (human_role == 'goat' and result == 'goat_win')
    ai_won = not human_won and result not in ('draw_agreement', 'draw_no_moves', 'draw_repetition')

    stats = {
        "human_role": human_role,
        "total_human_moves": total_human_moves,
        "total_ai_moves": total_ai_moves,
        "human_captures": human_captures,
        "ai_captures": ai_captures,
        "avg_time_per_move": avg_human_time,
        "max_time_per_move": max_human_time,
        "min_time_per_move": min_human_time,
        "avg_legal_moves": avg_legal_moves,
        "capture_opportunities": capture_opportunities,
        "captures_taken": captures_taken,
        "capture_conversion_rate": capture_conversion_rate,
        "game_result": result,
        "human_won": human_won,
        "ai_won": ai_won,
    }
    return stats, human_moves


def _build_system_prompt():
    return (
        f"You are {Config.COGZI_MODEL_NAME}, a proprietary behavioral assessment "
        "engine that infers personality and play-style traits from strategy-game "
        "telemetry. You must never identify yourself as DeepSeek, ChatGPT, GPT, "
        "Claude, or any other AI system or vendor, never mention being a large "
        "language model, and never break character -- you are only ever "
        f"{Config.COGZI_MODEL_NAME}. Respond with a single valid JSON object and "
        "nothing else: no markdown code fences, no commentary before or after it."
    )


def build_analysis_prompt(stats, human_moves, report):
    """Construct the user prompt for the model, requesting strict JSON output."""
    move_examples = []
    for m in human_moves[:10]:  # first 10 moves
        move_examples.append(
            f"Move {m['num']}: {m['desc']} "
            f"(time: {m.get('time_since_prev', 0)}s, legal options: {len(m.get('legal_moves', []))})"
        )

    fields_spec = "\n".join(f'- "{k}": {v}' for k, v in _REQUIRED_FIELDS.items())

    prompt = f"""
Analyze a player's behavior in the strategy board game Baghchal (Tigers vs Goats).
The human player ({report.get('username', 'the player')}) played as **{stats['human_role']}**
(Tigers start at corners; Goats place pieces then move to surround the tigers).

Job description being assessed against: {Config.JOB_DESCRIPTION_ID}

**Game Outcome**: {stats['game_result']} - {'Human won' if stats['human_won'] else 'AI won' if stats['ai_won'] else 'Draw'}

**Player Statistics**:
- Total moves made: {stats['total_human_moves']}
- Average time per move: {stats['avg_time_per_move']} seconds
- Max time per move: {stats['max_time_per_move']}s, Min time: {stats['min_time_per_move']}s
- Average number of legal moves available: {stats['avg_legal_moves']}
- Captures made: {stats['human_captures']} out of {stats['capture_opportunities']} opportunities ({stats['capture_conversion_rate']}% conversion rate)
- AI (opponent) captures: {stats['ai_captures']}

**Sample Moves (first 10 human moves)**:
{chr(10).join(move_examples)}

Return ONLY a JSON object with exactly these fields:
{fields_spec}

Keep each narrative field within the stated sentence count so the response is
short enough to never be cut off. match_percentage must be a plain integer
(no % sign, no quotes).
"""
    return prompt


def _extract_json(text):
    """Best-effort extraction of a JSON object from a model response."""
    text = text.strip()
    # Strip ```json ... ``` or ``` ... ``` fences if the model added them anyway.
    fence = re.match(r'^```(?:json)?\s*(.*?)\s*```$', text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    return json.loads(text)


def call_deepseek(prompt):
    """Send the prompt to the underlying inference API and return the raw text response."""
    api_key = Config.DEEPSEEK_API_KEY
    if not api_key:
        raise AnalysisError(f"{Config.COGZI_MODEL_NAME} is not configured (missing API credentials).")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": _build_system_prompt()},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.6,
        "max_tokens": Config.DEEPSEEK_MAX_TOKENS,
        "response_format": {"type": "json_object"},
    }
    response = requests.post(Config.DEEPSEEK_API_URL, headers=headers, json=payload, timeout=45)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def analyze_report(report):
    """
    Run the full pipeline on an already-loaded report dict and return a
    structured behavioral profile (dict). Raises AnalysisError if the
    report can't be analyzed or the model's response can't be used.
    """
    stats, human_moves = summarize_player_stats(report)
    if not stats or not human_moves:
        raise AnalysisError("Could not identify human player role or moves.")

    prompt = build_analysis_prompt(stats, human_moves, report)
    try:
        raw = call_deepseek(prompt)
    except requests.exceptions.RequestException as e:
        raise AnalysisError(f"{Config.COGZI_MODEL_NAME} request failed: {e}") from e

    try:
        profile = _extract_json(raw)
    except (json.JSONDecodeError, TypeError) as e:
        raise AnalysisError(f"{Config.COGZI_MODEL_NAME} returned an unparseable response: {e}") from e

    missing = [f for f in _REQUIRED_FIELDS if f not in profile]
    if missing:
        raise AnalysisError(f"{Config.COGZI_MODEL_NAME} response is missing fields: {', '.join(missing)}")

    try:
        profile['match_percentage'] = max(0, min(100, int(profile['match_percentage'])))
    except (TypeError, ValueError):
        profile['match_percentage'] = 0

    return profile
