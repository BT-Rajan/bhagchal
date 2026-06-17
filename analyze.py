"""
analyze.py — Reads a Baghchal game report (JSON) and uses DeepSeek API
to analyze the player's personality, play style, strengths, and weaknesses.
"""

import os
import json
import sys
from dotenv import load_dotenv
import requests

# Load environment variables from .env
load_dotenv()
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"  # or your endpoint

if not DEEPSEEK_API_KEY:
    print("Error: DEEPSEEK_API_KEY not set in .env file.")
    sys.exit(1)


def load_report(filepath):
    """Load the JSON game report."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def summarize_player_stats(report):
    """
    Extract and compute human-specific statistics from the report.
    Assumes the human role is given in report['human_role'].
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


def build_analysis_prompt(stats, human_moves, report):
    """Construct the prompt for DeepSeek API."""
    # Include a few sample moves to illustrate style
    move_examples = []
    for i, m in enumerate(human_moves[:10]):  # first 10 moves
        move_examples.append(f"Move {m['num']}: {m['desc']} (time: {m.get('time_since_prev', 0)}s, legal options: {len(m.get('legal_moves', []))})")

    prompt = f"""
You are an expert game analyst specializing in the ancient Indian board game Baghchal (Tigers vs Goats). 
The following data comes from a game where the human player played as **{stats['human_role']}** (Tigers start at corners, Goats place and move to surround).

**Game Outcome**: {stats['game_result']} – {'Human won' if stats['human_won'] else 'AI won' if stats['ai_won'] else 'Draw'}

**Player Statistics**:
- Total moves made: {stats['total_human_moves']}
- Average time per move: {stats['avg_time_per_move']} seconds
- Max time per move: {stats['max_time_per_move']}s, Min time: {stats['min_time_per_move']}s
- Average number of legal moves available: {stats['avg_legal_moves']}
- Captures made: {stats['human_captures']} out of {stats['capture_opportunities']} opportunities ({stats['capture_conversion_rate']}% conversion rate)
- AI (opponent) captures: {stats['ai_captures']}

**Sample Moves (first 10 human moves)**:
{chr(10).join(move_examples)}

Based on this data, provide a detailed personality and play style analysis of the human player. Include:
- Decision-making style (deliberate vs intuitive, risky vs conservative).
- Strategic strengths and weaknesses.
- Emotional/temperamental traits (patient, impulsive, aggressive, defensive).
- Pattern recognition and adaptability.
- Overall assessment and suggestions for improvement.

Write a concise, insightful personality profile (300-500 words).
"""
    return prompt


def call_deepseek(prompt):
    """Send the prompt to DeepSeek API and return the response."""
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek-chat",  # or "deepseek-reasoner" if you prefer
        "messages": [
            {"role": "system", "content": "You are an expert game analyst."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 800,
    }
    response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze.py <path_to_game_report.json>")
        sys.exit(1)

    report_path = sys.argv[1]
    report = load_report(report_path)

    stats, human_moves = summarize_player_stats(report)
    if not stats or not human_moves:
        print("Error: Could not identify human player role or moves.")
        sys.exit(1)

    prompt = build_analysis_prompt(stats, human_moves, report)
    print("Sending request to DeepSeek API...")
    try:
        analysis = call_deepseek(prompt)
        print("\n" + "="*60)
        print("🧠 PLAYER PERSONALITY ANALYSIS")
        print("="*60)
        print(analysis)
        print("="*60)

        # Optionally save analysis to a text file
        out_file = report_path.replace('.json', '_analysis.txt')
        with open(out_file, 'w', encoding='utf-8') as f:
            f.write(analysis)
        print(f"\nAnalysis saved to: {out_file}")

    except requests.exceptions.RequestException as e:
        print(f"API call failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()