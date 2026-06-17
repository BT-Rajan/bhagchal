"""
Game report export service.

Exports completed games to JSON files for analysis.
"""
import json
import os
import time
from datetime import datetime
from typing import Dict, Any

from baghchal.config import Config


class ReportService:
    """Handles game report generation and export."""
    
    def __init__(self):
        self.reports_dir = Config.REPORTS_DIR
        self._ensure_dir()
    
    def _ensure_dir(self) -> None:
        """Create reports directory if it doesn't exist."""
        if not os.path.exists(self.reports_dir):
            os.makedirs(self.reports_dir)
    
    def export_game_report(self, game: Dict[str, Any]) -> str:
        """Export a completed game to a JSON report file."""
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
        
        # Determine filename
        session_game_id = game.get('session_game_id')
        if session_game_id:
            filename = f"{session_game_id}.json"
        else:
            filename = (
                f"{game['id']}_{game['username']}_"
                f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
        
        # Build report
        end_time = game.get('end_time') or time.time()
        start_time = game.get('start_time', end_time)
        
        report = {
            'game_id': game['id'],
            'username': game['username'],
            'mode': game['mode'],
            'human_role': game['human_role'],
            'difficulty': game['difficulty'],
            'start_time': datetime.fromtimestamp(start_time).isoformat(),
            'end_time': datetime.fromtimestamp(end_time).isoformat() if end_time else None,
            'duration_seconds': round(end_time - start_time, 1),
            'status': s['status'],
            'total_moves': len(log),
            'move_log': moves_with_time,
            'final_state': {
                'board': s['board'],
                'goats_placed': s['goats_placed'],
                'goats_captured': s['goats_captured'],
                'phase': s['phase'],
                'tiger_moves': s['tiger_moves'],
                'goat_moves': s['goat_moves']
            },
            'session_game_id': session_game_id,
            'game_number': game.get('game_number'),
            'time_limit': game.get('time_limit')
        }
        
        # Write to file
        filepath = os.path.join(self.reports_dir, filename)
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2)
        
        return filepath


# Singleton instance
report_service = ReportService()
