"""
analyze.py — CLI tool to manually (re-)run a Cogzi Behavioral Intelligence
report on an existing game report (JSON), producing the same PDF the
automatic pipeline generates.

Note: this now happens automatically after every completed game (see
services/report.py -> services/analysis_service.py -> services/report_pdf.py
-> services/mailer.py). This script is for manually re-running or
backfilling a report that's already on disk.

Usage:
    python3 analyze.py <path_to_game_report.json>
"""
import json
import sys

from config import Config
from services.analysis_service import analyze_report, AnalysisError
from services.report_pdf import generate_pdf_report


def load_report(filepath):
    """Load the JSON game report."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze.py <path_to_game_report.json>")
        sys.exit(1)

    if not Config.DEEPSEEK_API_KEY:
        print(f"Error: {Config.COGZI_MODEL_NAME} is not configured (missing API credentials in .env).")
        sys.exit(1)

    report_path = sys.argv[1]
    report = load_report(report_path)

    print(f"Generating {Config.COGZI_MODEL_NAME} report...")
    try:
        profile = analyze_report(report)
    except AnalysisError as e:
        print(f"Error: {e}")
        sys.exit(1)

    out_file = report_path.replace('.json', '_analysis.pdf')
    generate_pdf_report(report, profile, out_file)

    print("\n" + "=" * 60)
    print(f"{Config.COGZI_MODEL_NAME.upper()} - SUMMARY")
    print("=" * 60)
    print(f"Traits: {', '.join(profile.get('traits', []))}")
    print(f"Match against {Config.JOB_DESCRIPTION_ID}: {profile.get('match_percentage')}%")
    print("=" * 60)
    print(f"\nFull report saved to: {out_file}")


if __name__ == "__main__":
    main()
