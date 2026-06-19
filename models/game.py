import json
import time
import uuid
from typing import Dict, Any, List, Optional, Tuple

from models.db import get_conn, tx


class SessionStore:

    def new_session(self, username: str) -> Dict[str, Any]:
        from models.user import user_model
        user = user_model.get_user(username)
        if not user:
            raise ValueError(f'Unknown user: {username}')
        sid = str(uuid.uuid4())
        with tx() as conn:
            conn.execute(
                'INSERT INTO sessions(id,user_id,org_id,current_game,finished) VALUES(?,?,?,1,0)',
                (sid, user['id'], user['org_id'])
            )
        return self.get_session(username)

    def get_session(self, username: str) -> Optional[Dict[str, Any]]:
        from models.user import user_model
        user = user_model.get_user(username)
        if not user:
            return None
        conn = get_conn()
        row = conn.execute(
            'SELECT * FROM sessions WHERE user_id=? ORDER BY created_at DESC LIMIT 1',
            (user['id'],)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d['session_id'] = d['id']
        return d

    def get_next_game_id(self, username: str) -> Tuple[Optional[str], Optional[int]]:
        sess = self.get_session(username)
        if not sess or sess['finished']:
            return None, None
        num = sess['current_game']
        if num > 5:
            with tx() as conn:
                conn.execute('UPDATE sessions SET finished=1 WHERE id=?', (sess['id'],))
            return None, None
        with tx() as conn:
            conn.execute('UPDATE sessions SET current_game=current_game+1 WHERE id=?', (sess['id'],))
        return sess['id'], num

    def mark_finished(self, username: str) -> None:
        sess = self.get_session(username)
        if sess:
            with tx() as conn:
                conn.execute("UPDATE sessions SET finished=1,completed_at=datetime('now') WHERE id=?", (sess['id'],))


class GameStore:

    def new_game(self, username: str, mode: str, human_role: str,
                 difficulty: str = 'medium', session_game_id: str = None) -> str:
        from models.user import user_model
        from services.engine import init_state
        user = user_model.get_user(username)
        if not user:
            raise ValueError(f'Unknown user: {username}')
        gid = str(uuid.uuid4())
        state = init_state()
        now = time.time()
        # parse session_game_id: "SESSION_UUID_001" → session_id=SESSION_UUID
        sess_id = None
        if session_game_id:
            parts = session_game_id.rsplit('_', 1)
            if len(parts) == 2:
                sess_id = parts[0]

        game_obj = {
            'id': gid, 'username': username, 'mode': mode,
            'human_role': human_role, 'difficulty': difficulty,
            'state': state, 'move_log': [],
            'draw_offered': False, 'draw_off_by': None, 'prev_state': None,
            'start_time': now, 'end_time': None,
            'session_game_id': session_game_id,
            'game_number': None, 'time_limit': None, 'time_remaining': None,
        }
        with tx() as conn:
            conn.execute(
                '''INSERT INTO games(id,session_id,user_id,org_id,mode,human_role,difficulty,
                   status,state_json,move_log_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?)''',
                (gid, sess_id, user['id'], user['org_id'],
                 mode, human_role, difficulty, 'active',
                 json.dumps(state), '[]')
            )
        # cache in memory for the session
        _game_cache[gid] = game_obj
        return gid

    def get_game(self, game_id: str) -> Optional[Dict[str, Any]]:
        if game_id in _game_cache:
            return _game_cache[game_id]
        conn = get_conn()
        row = conn.execute('SELECT * FROM games WHERE id=?', (game_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        from models.user import user_model
        user = user_model.get_user_by_id(d['user_id'])
        game = {
            'id': d['id'],
            'username': user['username'] if user else '',
            'mode': d['mode'],
            'human_role': d['human_role'],
            'difficulty': d['difficulty'],
            'state': json.loads(d['state_json']),
            'move_log': json.loads(d['move_log_json']),
            'draw_offered': False, 'draw_off_by': None, 'prev_state': None,
            'start_time': d.get('start_time') or time.time(),
            'end_time': d.get('end_time'),
            'session_game_id': None,
            'game_number': d.get('game_number'),
            'time_limit': d.get('time_limit'),
            'time_remaining': None,
        }
        _game_cache[game_id] = game
        return game

    def save_game(self, game: Dict[str, Any]) -> None:
        _game_cache[game['id']] = game
        s = game['state']
        with tx() as conn:
            conn.execute(
                '''UPDATE games SET status=?,state_json=?,move_log_json=?,end_time=?,
                   duration_sec=?,time_limit=? WHERE id=?''',
                (s['status'],
                 json.dumps(s),
                 json.dumps(game['move_log']),
                 game.get('end_time'),
                 (game['end_time'] - game['start_time']) if game.get('end_time') else None,
                 game.get('time_limit'),
                 game['id'])
            )

    def add_move_log(self, game: Dict, faction: str, desc: str,
                     is_capture: bool = False, timestamp: float = None,
                     legal_moves: List[str] = None) -> None:
        game['move_log'].append({
            'num': len(game['move_log']) + 1,
            'faction': faction, 'desc': desc,
            'is_capture': is_capture,
            'timestamp': timestamp if timestamp is not None else time.time(),
            'legal_moves': legal_moves or [],
        })


# In-memory cache keyed by game_id (avoids repeated DB round-trips mid-game)
_game_cache: Dict[str, Any] = {}


session_store = SessionStore()
game_store    = GameStore()
