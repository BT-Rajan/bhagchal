"""
analyze.py — CLI tool to re-run personality analysis on an existing game
report (JSON) using the DeepSeek API.

Note: this now happens automatically after every completed game (see
services/report.py -> services/analysis_service.py -> services/mailer.py).
This script is for manually re-running or backfilling analysis on a report
that's already on disk.

Usage:
    python3 analyze.py <path_to_game_report.json>
"""
import json
import sys

from config import Config
from services.analysis_service import analyze_report, AnalysisError


def load_report(filepath):
    """Load the JSON game report."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze.py <path_to_game_report.json>")
        sys.exit(1)

    if not Config.DEEPSEEK_API_KEY:
        print("Error: DEEPSEEK_API_KEY not set in .env file.")
        sys.exit(1)

    report_path = sys.argv[1]
    report = load_report(report_path)

    print("Sending request to DeepSeek API...")
    try:
        analysis = analyze_report(report)
    except AnalysisError as e:
        print(f"Error: {e}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("🧠 PLAYER PERSONALITY ANALYSIS")
    print("=" * 60)
    print(analysis)
    print("=" * 60)

    # Save analysis to a text file alongside the report
    out_file = report_path.replace('.json', '_analysis.txt')
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write(analysis)
    print(f"\nAnalysis saved to: {out_file}")


if __name__ == "__main__":
    main()
