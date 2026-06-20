import hashlib, hmac, secrets, time, uuid, json
from typing import Optional, Tuple, Dict, Any, List
from models.db import get_conn, tx

class UserModel:

    def _hash(self, pw):
        return hashlib.sha256(pw.encode()).hexdigest()

    def _check(self, stored, pw):
        return hmac.compare_digest(stored, self._hash(pw))

    def _default_org(self):
        row = get_conn().execute('SELECT id FROM organizations LIMIT 1').fetchone()
        return row['id'] if row else None

    # ── Auth ──────────────────────────────────────────────────────────────

    def register(self, username, password, email='', org_id=None, role='user') -> Tuple[bool, Any]:
        if not username or len(username) < 2:
            return False, 'Username must be at least 2 characters.'
        if not all(c.isalnum() or c == '_' for c in username):
            return False, 'Username: letters, numbers, underscores only.'
        if not password or len(password) < 4:
            return False, 'Password must be at least 4 characters.'
        if org_id is None:
            org_id = self._default_org()
        with tx() as conn:
            if conn.execute('SELECT id FROM users WHERE username=? COLLATE NOCASE',(username,)).fetchone():
                return False, 'Username already taken.'
            uid = str(uuid.uuid4())
            conn.execute(
                'INSERT INTO users(id,org_id,username,email,password_hash,role) VALUES(?,?,?,?,?,?)',
                (uid, org_id, username, email, self._hash(password), role))
        return True, self.get_user(username)

    def login(self, username, password) -> Tuple[bool, Any]:
        user = get_conn().execute(
            'SELECT * FROM users WHERE username=? COLLATE NOCASE',(username,)).fetchone()
        dummy = self._hash('')
        stored = user['password_hash'] if user else dummy
        if not user or not self._check(stored, password):
            return False, 'Invalid username or password.'
        if user['suspended']:
            return False, 'Account suspended. Contact your administrator.'
        with tx() as c:
            c.execute("UPDATE users SET last_login=datetime('now') WHERE id=?",(user['id'],))
        return True, dict(user)

    # ── Getters ───────────────────────────────────────────────────────────

    def get_user(self, username) -> Optional[Dict]:
        row = get_conn().execute(
            'SELECT * FROM users WHERE username=? COLLATE NOCASE',(username,)).fetchone()
        return dict(row) if row else None

    def get_user_by_id(self, uid) -> Optional[Dict]:
        row = get_conn().execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
        return dict(row) if row else None

    def all_users(self, org_id=None, role=None, search=None) -> List[Dict]:
        sql = 'SELECT * FROM users WHERE 1=1'
        params = []
        if org_id:
            sql += ' AND org_id=?'; params.append(org_id)
        if role:
            sql += ' AND role=?'; params.append(role)
        if search:
            sql += ' AND (username LIKE ? OR email LIKE ?)'; params += [f'%{search}%']*2
        sql += ' ORDER BY created_at DESC'
        rows = get_conn().execute(sql, params).fetchall()
        return [{k:v for k,v in dict(r).items() if k != 'password_hash'} for r in rows]

    # ── Admin CRUD ────────────────────────────────────────────────────────

    def create_user(self, username, password, email='', role='user', org_id=None) -> Tuple[bool, Any]:
        if role not in ('admin','sponsor','user'):
            return False, 'Invalid role.'
        return self.register(username, password, email, org_id, role)

    def update_user(self, username, updates: Dict) -> Tuple[bool, str]:
        user = self.get_user(username)
        if not user:
            return False, 'User not found.'
        allowed = {'email','role','password'}
        sets, params = [], []
        for k, v in updates.items():
            if k not in allowed:
                continue
            if k == 'password':
                sets.append('password_hash=?'); params.append(self._hash(v))
            elif k == 'role':
                if v not in ('admin','sponsor','user'):
                    return False, 'Invalid role.'
                sets.append('role=?'); params.append(v)
            else:
                sets.append(f'{k}=?'); params.append(v)
        if not sets:
            return False, 'Nothing to update.'
        params.append(username)
        with tx() as conn:
            conn.execute(f"UPDATE users SET {','.join(sets)} WHERE username=?", params)
        return True, 'Updated.'

    def delete_user(self, username) -> bool:
        user = get_conn().execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
        if not user or user['role'] == 'admin':
            return False
        with tx() as c:
            c.execute('DELETE FROM users WHERE username=?',(username,))
        return True

    def suspend_user(self, username, suspend=True) -> Tuple[bool, str]:
        user = self.get_user(username)
        if not user:
            return False, 'User not found.'
        if user['role'] == 'admin':
            return False, 'Cannot suspend admin.'
        with tx() as conn:
            conn.execute('UPDATE users SET suspended=? WHERE username=?',(1 if suspend else 0, username))
        return True, 'Suspended.' if suspend else 'Reinstated.'

    def increment_games(self, username):
        with tx() as conn:
            conn.execute('UPDATE users SET games_played=games_played+1 WHERE username=?',(username,))

    # ── Bundles ───────────────────────────────────────────────────────────

    def get_bundles(self, org_id=None) -> List[Dict]:
        sql = 'SELECT b.*,u.username as creator FROM game_bundles b JOIN users u ON b.created_by=u.id'
        params = []
        if org_id:
            sql += ' WHERE b.org_id=?'; params.append(org_id)
        sql += ' ORDER BY b.created_at DESC'
        return [dict(r) for r in get_conn().execute(sql, params).fetchall()]

    def create_bundle(self, name, depth, game_count, created_by, org_id, description='') -> Dict:
        bid = str(uuid.uuid4())
        depth = max(1, min(int(depth), 6))
        game_count = max(1, min(int(game_count), 10))
        with tx() as conn:
            conn.execute(
                'INSERT INTO game_bundles(id,org_id,created_by,name,description,depth,game_count) VALUES(?,?,?,?,?,?,?)',
                (bid, org_id, created_by, name, description, depth, game_count))
        return {'id': bid, 'name': name, 'depth': depth, 'game_count': game_count}

    def update_bundle(self, bundle_id, updates: Dict) -> Tuple[bool, str]:
        allowed = {'name','description','depth','game_count'}
        sets, params = [], []
        for k, v in updates.items():
            if k not in allowed: continue
            if k == 'depth':   v = max(1, min(int(v), 6))
            if k == 'game_count': v = max(1, min(int(v), 10))
            sets.append(f'{k}=?'); params.append(v)
        if not sets:
            return False, 'Nothing to update.'
        params.append(bundle_id)
        with tx() as conn:
            conn.execute(f"UPDATE game_bundles SET {','.join(sets)} WHERE id=?", params)
        return True, 'Updated.'

    def delete_bundle(self, bundle_id) -> bool:
        with tx() as conn:
            conn.execute('DELETE FROM bundle_assignments WHERE bundle_id=?',(bundle_id,))
            conn.execute('DELETE FROM game_bundles WHERE id=?',(bundle_id,))
        return True

    def assign_bundle(self, bundle_id, assigned_to_username, assigned_by_id) -> Tuple[bool, str]:
        user = self.get_user(assigned_to_username)
        if not user:
            return False, 'User not found.'
        if user['role'] != 'user':
            return False, 'Bundles can only be assigned to users.'
        existing = get_conn().execute(
            "SELECT id FROM bundle_assignments WHERE bundle_id=? AND assigned_to=? AND status='pending'",
            (bundle_id, user['id'])).fetchone()
        if existing:
            return False, 'Bundle already assigned to this user.'
        with tx() as conn:
            conn.execute(
                'INSERT INTO bundle_assignments(id,bundle_id,assigned_to,assigned_by) VALUES(?,?,?,?)',
                (str(uuid.uuid4()), bundle_id, user['id'], assigned_by_id))
        return True, 'Assigned.'

    def get_user_bundles(self, username) -> List[Dict]:
        user = self.get_user(username)
        if not user: return []
        rows = get_conn().execute(
            '''SELECT b.*,ba.status as assign_status,ba.assigned_at
               FROM bundle_assignments ba
               JOIN game_bundles b ON ba.bundle_id=b.id
               WHERE ba.assigned_to=?
               ORDER BY ba.assigned_at DESC''',
            (user['id'],)).fetchall()
        return [dict(r) for r in rows]

    # ── Invites ───────────────────────────────────────────────────────────

    def create_invite(self, email, invited_by_id, org_id, role='user', bundle_id=None) -> str:
        token = secrets.token_hex(16)
        expires = time.strftime('%Y-%m-%d %H:%M:%S',
                                time.gmtime(time.time() + 7*24*3600))
        with tx() as conn:
            conn.execute(
                'INSERT INTO invites(id,org_id,invited_by,email,role,token,bundle_id,expires_at) VALUES(?,?,?,?,?,?,?,?)',
                (str(uuid.uuid4()), org_id, invited_by_id, email, role, token, bundle_id, expires))
        return token

    def use_invite(self, token) -> Optional[Dict]:
        row = get_conn().execute(
            "SELECT * FROM invites WHERE token=? AND used=0 AND expires_at > datetime('now')",
            (token,)).fetchone()
        if not row: return None
        with tx() as conn:
            conn.execute('UPDATE invites SET used=1 WHERE id=?',(row['id'],))
        return dict(row)

    def list_invites(self, org_id=None, invited_by_id=None) -> List[Dict]:
        sql = 'SELECT * FROM invites WHERE 1=1'
        params = []
        if org_id:
            sql += ' AND org_id=?'; params.append(org_id)
        if invited_by_id:
            sql += ' AND invited_by=?'; params.append(invited_by_id)
        sql += ' ORDER BY created_at DESC'
        return [dict(r) for r in get_conn().execute(sql, params).fetchall()]

    # ── Password reset ────────────────────────────────────────────────────

    def generate_reset_token(self, username) -> Optional[str]:
        user = self.get_user(username)
        if not user: return None
        token = secrets.token_hex(6).upper()
        meta = json.loads(user.get('metadata') or '{}')
        meta['reset_token']   = token
        meta['reset_expires'] = time.time() + 300
        with tx() as conn:
            conn.execute('UPDATE users SET metadata=? WHERE username=?',(json.dumps(meta), username))
        return token

    def reset_password(self, username, token, new_password) -> Tuple[bool, str]:
        if not new_password or len(new_password) < 4:
            return False, 'Password must be at least 4 characters.'
        user = self.get_user(username)
        if not user: return False, 'Invalid token.'
        meta = json.loads(user.get('metadata') or '{}')
        if not hmac.compare_digest(meta.get('reset_token',''), token):
            return False, 'Invalid token.'
        if time.time() > meta.get('reset_expires', 0):
            return False, 'Token expired.'
        meta.pop('reset_token', None); meta.pop('reset_expires', None)
        with tx() as conn:
            conn.execute('UPDATE users SET password_hash=?,metadata=? WHERE username=?',
                         (self._hash(new_password), json.dumps(meta), username))
        return True, 'Password reset successfully.'

user_model = UserModel()
