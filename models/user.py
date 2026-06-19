import hashlib
import hmac
import secrets
import time
import uuid
from typing import Optional, Tuple, Dict, Any

from models.db import get_conn, tx


class UserModel:

    def _hash(self, pw: str) -> str:
        return hashlib.sha256(pw.encode()).hexdigest()

    def _check(self, stored: str, pw: str) -> bool:
        return hmac.compare_digest(stored, self._hash(pw))

    def register(self, username: str, password: str, email: str = '', org_id: str = None) -> Tuple[bool, Any]:
        if not username or len(username) < 2:
            return False, 'Username must be at least 2 characters.'
        if not all(c.isalnum() or c == '_' for c in username):
            return False, 'Username: letters, numbers, underscores only.'
        if not password or len(password) < 4:
            return False, 'Password must be at least 4 characters.'

        if org_id is None:
            conn = get_conn()
            row = conn.execute('SELECT id FROM organizations LIMIT 1').fetchone()
            org_id = row['id'] if row else None

        with tx() as conn:
            exists = conn.execute('SELECT id FROM users WHERE username=? COLLATE NOCASE', (username,)).fetchone()
            if exists:
                return False, 'Username already taken.'
            uid = str(uuid.uuid4())
            conn.execute(
                'INSERT INTO users(id,org_id,username,email,password_hash,role) VALUES(?,?,?,?,?,?)',
                (uid, org_id, username, email, self._hash(password), 'user')
            )

        return True, self.get_user(username)

    def login(self, username: str, password: str) -> Tuple[bool, Any]:
        conn = get_conn()
        user = conn.execute('SELECT * FROM users WHERE username=? COLLATE NOCASE', (username,)).fetchone()
        dummy = self._hash('')
        stored = user['password_hash'] if user else dummy
        if not user or not self._check(stored, password):
            return False, 'Invalid username or password.'
        with tx() as c:
            c.execute("UPDATE users SET last_login=datetime('now') WHERE id=?", (user['id'],))
        return True, dict(user)

    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        conn = get_conn()
        row = conn.execute('SELECT * FROM users WHERE username=? COLLATE NOCASE', (username,)).fetchone()
        return dict(row) if row else None

    def get_user_by_id(self, uid: str) -> Optional[Dict[str, Any]]:
        conn = get_conn()
        row = conn.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
        return dict(row) if row else None

    def all_users(self, org_id: str = None) -> list:
        conn = get_conn()
        if org_id:
            rows = conn.execute('SELECT * FROM users WHERE org_id=? ORDER BY created_at DESC', (org_id,)).fetchall()
        else:
            rows = conn.execute('SELECT * FROM users ORDER BY created_at DESC').fetchall()
        return [{k: v for k, v in dict(r).items() if k != 'password_hash'} for r in rows]

    def increment_games(self, username: str) -> None:
        with tx() as conn:
            conn.execute('UPDATE users SET games_played=games_played+1 WHERE username=?', (username,))

    def delete_user(self, username: str) -> bool:
        conn = get_conn()
        user = conn.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        if not user or user['role'] == 'admin':
            return False
        with tx() as c:
            c.execute('DELETE FROM users WHERE username=?', (username,))
        return True

    def generate_reset_token(self, username: str) -> Optional[str]:
        user = self.get_user(username)
        if not user:
            return None
        token = secrets.token_hex(6).upper()
        with tx() as conn:
            import json
            meta = json.loads(user.get('metadata') or '{}')
            meta['reset_token'] = token
            meta['reset_expires'] = time.time() + 300
            conn.execute('UPDATE users SET metadata=? WHERE username=?', (json.dumps(meta), username))
        return token

    def reset_password(self, username: str, token: str, new_password: str) -> Tuple[bool, str]:
        import json
        if not new_password or len(new_password) < 4:
            return False, 'Password must be at least 4 characters.'
        user = self.get_user(username)
        if not user:
            return False, 'Invalid token.'
        meta = json.loads(user.get('metadata') or '{}')
        stored_tok = meta.get('reset_token', '')
        expires    = meta.get('reset_expires', 0)
        if not hmac.compare_digest(stored_tok, token):
            return False, 'Invalid token.'
        if time.time() > expires:
            return False, 'Token expired.'
        meta.pop('reset_token', None)
        meta.pop('reset_expires', None)
        with tx() as conn:
            conn.execute('UPDATE users SET password_hash=?,metadata=? WHERE username=?',
                         (self._hash(new_password), json.dumps(meta), username))
        return True, 'Password reset successfully.'


user_model = UserModel()
