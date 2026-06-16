"""
report.py — Export game report to JSON after completion.
"""
import json
import os
import time
from datetime import datetime

REPORTS_DIR = 'game_reports'

def ensure_dir():
    if not os.path.exists(REPORTS_DIR):
        os.makedirs(REPORTS_DIR)
        print(f"[report] Created directory: {REPORTS_DIR}")

def export_game_report(game):
    ensure_dir()
    s = game['state']
    log = game['move_log']

    # Compute time per move
    moves_with_time = []
    prev_ts = game.get('start_time', time.time())
    for entry in log:
        ts = entry.get('timestamp', prev_ts)
        moves_with_time.append({
            **entry,
            'time_since_prev': round(ts - prev_ts, 3)
        })
        prev_ts = ts

    # Determine filename: use session_game_id if available
    session_game_id = game.get('session_game_id')
    if session_game_id:
        filename = f"{session_game_id}.json"
    else:
        # fallback to old naming
        filename = f"{game['id']}_{game['username']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    report = {
        'game_id': game['id'],
        'username': game['username'],
        'mode': game['mode'],
        'human_role': game['human_role'],
        'difficulty': game['difficulty'],
        'start_time': datetime.fromtimestamp(game.get('start_time', time.time())).isoformat(),
        'end_time': datetime.fromtimestamp(game.get('end_time', time.time())).isoformat() if game.get('end_time') else None,
        'duration_seconds': round(game.get('end_time', time.time()) - game.get('start_time', time.time()), 1) if game.get('end_time') else None,
        'status': s['status'],
        'total_moves': len(log),
        'move_log': moves_with_time,
        'final_state': {
            'board': s['board'],
            'goats_placed': s['goats_placed'],
            'goats_captured': s['goats_captured'],
            'phase': s['phase'],
            'tiger_moves': s['tiger_moves'],
            'goat_moves': s['goat_moves'],
        },
        'session_game_id': session_game_id,
        'game_number': game.get('game_number'),
        'time_limit': game.get('time_limit'),
    }

    filepath = os.path.join(REPORTS_DIR, filename)
    with open(filepath, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"[report] Exported game report to {filepath}")
    return filepath