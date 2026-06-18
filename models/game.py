"""
Game session and state management.

In-memory game store (swap for database in production).
"""
import uuid
import time
from typing import Dict, Any, List, Optional, Tuple


class SessionStore:
    """Manages user game sessions (one active session per user)."""

    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def new_session(self, username: str) -> Dict[str, Any]:
        """Create a new 5-game session for the user."""
        session_id = str(uuid.uuid4())[:8].upper()
        session = {
            'username':    username,
            'session_id':  session_id,
            'games':       {},      # game_number → game_id
            'current_game': 1,      # 1..MAX_SESSION_GAMES
            'created_at':  time.time(),
            'finished':    False,
        }
        self._sessions[username] = session
        return session

    def get_session(self, username: str) -> Optional[Dict[str, Any]]:
        """Get session by username."""
        return self._sessions.get(username)

    def get_next_game_id(self, username: str) -> Tuple[Optional[str], Optional[int]]:
        """Reserve and return the next (game_id, game_number) slot."""
        session = self.get_session(username)
        if not session or session['finished']:
            return None, None

        num = session['current_game']
        if num > 5:
            session['finished'] = True
            return None, None

        # game_id will be set by GameStore.new_game; store a placeholder key
        session['games'][num] = None
        session['current_game'] = num + 1
        return str(uuid.uuid4()), num   # caller must call game_store.new_game with the session_game_id

    def mark_finished(self, username: str) -> None:
        """Mark session as completed."""
        session = self.get_session(username)
        if session:
            session['finished'] = True


class GameStore:
    """Manages individual game instances."""

    def __init__(self):
        self._games: Dict[str, Dict[str, Any]] = {}

    def new_game(
        self,
        username: str,
        mode: str,
        human_role: str,
        difficulty: str = 'medium',
        session_game_id: Optional[str] = None,
    ) -> str:
        """Create a new game instance and return its game_id."""
        from services.engine import init_state

        game_id = str(uuid.uuid4())
        self._games[game_id] = {
            'id':             game_id,
            'username':       username,
            'mode':           mode,
            'human_role':     human_role,
            'difficulty':     difficulty,
            'state':          init_state(),
            'move_log':       [],
            'draw_offered':   False,
            'draw_off_by':    None,
            'prev_state':     None,
            'created_at':     time.time(),
            'updated_at':     time.time(),
            'start_time':     time.time(),
            'end_time':       None,
            'session_game_id': session_game_id,
            'game_number':    None,
            'time_limit':     None,
            'time_remaining': None,
        }
        return game_id

    def get_game(self, game_id: str) -> Optional[Dict[str, Any]]:
        """Get game by ID."""
        return self._games.get(game_id)

    def save_game(self, game: Dict[str, Any]) -> None:
        """Persist updated game state."""
        game['updated_at'] = time.time()
        self._games[game['id']] = game

    def add_move_log(
        self,
        game: Dict[str, Any],
        faction: str,
        desc: str,
        is_capture: bool = False,
        timestamp: Optional[float] = None,
        legal_moves: Optional[List[str]] = None,
    ) -> None:
        """Append a move entry to the game log."""
        game['move_log'].append({
            'num':         len(game['move_log']) + 1,
            'faction':     faction,
            'desc':        desc,
            'is_capture':  is_capture,
            'timestamp':   timestamp if timestamp is not None else time.time(),
            'legal_moves': legal_moves or [],
        })


# Singleton instances
session_store = SessionStore()
game_store = GameStore()
