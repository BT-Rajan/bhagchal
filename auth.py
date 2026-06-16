"""
auth.py — In-memory user store and session management.
No browser storage. Server owns all state.
"""
import hashlib, secrets, time
from functools import wraps
from flask import session, jsonify

# ── In-memory stores (reset on server restart — swap for DB in production) ──
_users  = {}   # username.lower() → {username, password_hash, role, created_at, games_played}
_tokens = {}   # username.lower() → {token, expires}

def _hash(password):
    return hashlib.sha256(password.encode()).hexdigest()

def _seed_defaults():
    for uname, pwd, role in [('admin','admin','admin'), ('guest','guest','user')]:
        key = uname.lower()
        _users[key] = {
            'username':     uname,
            'password_hash': _hash(pwd),
            'role':          role,
            'created_at':    '2024-01-01',
            'games_played':  0,
        }

_seed_defaults()


# ── Public API ────────────────────────────────────────────────────────────────

def register(username, password, email=''):
    if not username or len(username) < 2:
        return False, 'Username must be at least 2 characters.'
    if not all(c.isalnum() or c == '_' for c in username):
        return False, 'Username: letters, numbers, underscores only.'
    if not password or len(password) < 4:
        return False, 'Password must be at least 4 characters.'
    key = username.lower()
    if key in _users:
        return False, 'Username already taken.'
    _users[key] = {
        'username':      username,
        'password_hash': _hash(password),
        'role':          'user',
        'created_at':    time.strftime('%Y-%m-%d'),
        'games_played':  0,
        'email':         email,
    }
    return True, _users[key]


def login(username, password):
    key = username.lower()
    user = _users.get(key)
    if not user:
        return False, 'User not found.'
    if user['password_hash'] != _hash(password):
        return False, 'Incorrect password.'
    return True, user


def get_user(username):
    return _users.get(username.lower())


def all_users():
    return list(_users.values())


def delete_user(username):
    key = username.lower()
    user = _users.get(key)
    if user and user['role'] != 'admin':
        del _users[key]


def increment_games(username):
    user = _users.get(username.lower())
    if user:
        user['games_played'] = user.get('games_played', 0) + 1


def generate_reset_token(username):
    user = _users.get(username.lower())
    if not user:
        return None
    token = secrets.token_hex(6).upper()
    _tokens[username.lower()] = {'token': token, 'expires': time.time() + 300}
    return token


def reset_password(username, token, new_password):
    if not new_password or len(new_password) < 4:
        return False, 'Password must be at least 4 characters.'
    key = username.lower()
    entry = _tokens.get(key)
    if not entry or entry['token'] != token:
        return False, 'Invalid token.'
    if time.time() > entry['expires']:
        return False, 'Token expired.'
    user = _users.get(key)
    if not user:
        return False, 'User not found.'
    user['password_hash'] = _hash(new_password)
    del _tokens[key]
    return True, 'Password reset successfully.'


# ── Flask session helpers ─────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'username' not in session:
            return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'username' not in session:
            return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
        user = get_user(session['username'])
        if not user or user['role'] != 'admin':
            return jsonify({'ok': False, 'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated


def current_user():
    if 'username' not in session:
        return None
    return get_user(session['username'])
