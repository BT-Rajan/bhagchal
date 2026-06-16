"""Utility decorators and helpers."""

from functools import wraps
from flask import session, jsonify

from baghchal.models.user import user_model


def login_required(f):
    """Decorator to require authentication for a route."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'username' not in session:
            return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """Decorator to require admin role for a route."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'username' not in session:
            return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
        
        user = user_model.get_user(session['username'])
        if not user or user['role'] != 'admin':
            return jsonify({'ok': False, 'error': 'Admin access required'}), 403
        
        return f(*args, **kwargs)
    return decorated


def current_user():
    """Get the currently logged-in user."""
    if 'username' not in session:
        return None
    return user_model.get_user(session['username'])
