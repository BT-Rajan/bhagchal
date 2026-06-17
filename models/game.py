"""
Game session and state management.

In-memory game store (swap for database in production).
"""
import uuid
import time
from typing import Optional, Dict, Any, List


class SessionStore:
    """Manages user game sessions."""
    
    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}
    
    def new_session(self, username: str) -> Dict[str, Any]:
        """Create a new 5-game session for the user."""
        session_id = str(uuid.uuid4())[:8].upper()
        session = {
            'username': username,
            'session_id': session_id,
            'games': {},  # game_number → game_id
            'current_game': 1,  # 1..5
            'created_at': time.time(),
            'finished': False
        }
        self._sessions[username] = session
        return session
    
    def get_session(self, username: str) -> Optional[Dict[str, Any]]:
        """Get session by username."""
        return self._sessions.get(username)
    
    def get_next_game_id(self, username: str) -> tuple:
        """Get the next game number and create its game_id."""
        session = self.get_session(username)
        if not session or session['finished']:
            return None, None
        
        num = session['current_game']
        if num > 5:
            session['finished'] = True
            return None, None
        
        game_id = f"{session['session_id']}_{num:03d}"
        session['games'][num] = game_id
        session['current_game'] = num + 1
        return game_id, num
    
    def mark_finished(self, username: str) -> None:
        """Mark session as finished."""
        session = self.get_session(username)
        if session:
            session['finished'] = True


class GameStore:
    """Manages individual game instances."""
    
    def __init__(self):
        self._games: Dict[str, Dict[str, Any]] = {}
    
    def new_game(self, username: str, mode: str, human_role: str, difficulty: str = 'medium') -> str:
        """Create a new game instance."""
        from services.engine import init_state
        
        game_id = str(uuid.uuid4())
        self._games[game_id] = {
            'id': game_id,
            'username': username,
            'mode': mode,
            'human_role': human_role,
            'difficulty': difficulty,
            'state': init_state(),
            'move_log': [],
            'draw_offered': False,
            'draw_off_by': None,
            'prev_state': None,
            'ai_thinking': False,
            'created_at': time.time(),
            'updated_at': time.time(),
            'start_time': time.time(),
            'end_time': None,
            'session_game_id': None,
            'game_number': None,
            'time_limit': None,
            'time_remaining': None
        }
        return game_id
    
    def get_game(self, game_id: str) -> Optional[Dict[str, Any]]:
        """Get game by ID."""
        return self._games.get(game_id)
    
    def save_game(self, game: Dict[str, Any]) -> None:
        """Save/update game state."""
        game['updated_at'] = time.time()
        self._games[game['id']] = game
    
    def add_move_log(
        self, 
        game: Dict[str, Any], 
        faction: str, 
        desc: str, 
        is_capture: bool = False,
        timestamp: Optional[float] = None,
        legal_moves: Optional[List[str]] = None
    ) -> None:
        """Add a move to the game log."""
        if timestamp is None:
            timestamp = time.time()
        
        game['move_log'].append({
            'num': len(game['move_log']) + 1,
            'faction': faction,
            'desc': desc,
            'is_capture': is_capture,
            'timestamp': timestamp,
            'legal_moves': legal_moves or []
        })


# Singleton instances
session_store = SessionStore()
game_store = GameStore()
