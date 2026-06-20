from functools import wraps
from flask import session, jsonify
from models.user import user_model

def _get_user():
    un = session.get('username')
    return user_model.get_user(un) if un else None

def login_required(f):
    @wraps(f)
    def decorated(*a, **kw):
        if not session.get('username'):
            return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
        return f(*a, **kw)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*a, **kw):
        user = _get_user()
        if not user:
            return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
        if user['role'] != 'admin':
            return jsonify({'ok': False, 'error': 'Admin access required'}), 403
        return f(*a, **kw)
    return decorated

def sponsor_required(f):
    @wraps(f)
    def decorated(*a, **kw):
        user = _get_user()
        if not user:
            return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
        if user['role'] not in ('admin', 'sponsor'):
            return jsonify({'ok': False, 'error': 'Sponsor access required'}), 403
        return f(*a, **kw)
    return decorated

def current_user():
    return _get_user()
