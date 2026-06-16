"""
game_store.py — Server-side game session store.
"""
import uuid
import time

_games = {}      # game_id → game session dict
_sessions = {}   # username → session dict


def new_session(username):
    """Create a new 5-game session for the user."""
    session_id = str(uuid.uuid4())[:8].upper()
    session = {
        'username': username,
        'session_id': session_id,
        'games': {},          # game_number → game_id
        'current_game': 1,    # 1..5
        'created_at': time.time(),
        'finished': False,
    }
    _sessions[username] = session
    return session


def get_session(username):
    return _sessions.get(username)


def get_next_game_id(username):
    """Get the next game number and create its game_id."""
    session = get_session(username)
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


def new_game(username, mode, human_role, difficulty='medium'):
    """Create a new game (used for all 5 games)."""
    from engine import init_state
    game_id = str(uuid.uuid4())
    _games[game_id] = {
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
        'session_game_id': None,   # will be set
        'game_number': None,
        'time_limit': None,        # for timed game (seconds)
        'time_remaining': None,
    }
    return game_id


def get_game(game_id):
    return _games.get(game_id)


def save_game(game):
    game['updated_at'] = time.time()
    _games[game['id']] = game


def add_move_log(game, faction, desc, is_capture=False, timestamp=None, legal_moves=None):
    if timestamp is None:
        timestamp = time.time()
    game['move_log'].append({
        'num': len(game['move_log']) + 1,
        'faction': faction,
        'desc': desc,
        'is_capture': is_capture,
        'timestamp': timestamp,
        'legal_moves': legal_moves or [],
    })


def mark_session_finished(username):
    session = get_session(username)
    if session:
        session['finished'] = True