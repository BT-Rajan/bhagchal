"""
Authentication API routes.

Handles login, register, logout, password reset.
"""
from flask import Blueprint, request, jsonify, session

from models.user import user_model

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


@auth_bp.route('/login', methods=['POST'])
def login():
    """Authenticate user and create session."""
    data = request.get_json() or {}
    username = data.get('username', '')
    password = data.get('password', '')
    
    success, result = user_model.login(username, password)
    
    if not success:
        return jsonify({'ok': False, 'error': result}), 400
    
    session['username'] = result['username']
    session['role'] = result['role']
    
    return jsonify({
        'ok': True,
        'username': result['username'],
        'role': result['role']
    })


@auth_bp.route('/register', methods=['POST'])
def register():
    """Create new user account and auto-login."""
    data = request.get_json() or {}
    username = data.get('username', '')
    password = data.get('password', '')
    email = data.get('email', '')
    
    success, result = user_model.register(username, password, email)
    
    if not success:
        return jsonify({'ok': False, 'error': result}), 400
    
    # Auto-login
    session['username'] = result['username']
    session['role'] = result['role']
    
    return jsonify({
        'ok': True,
        'username': result['username'],
        'role': result['role']
    })


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """Clear user session."""
    session.clear()
    return jsonify({'ok': True})


@auth_bp.route('/forgot', methods=['POST'])
def forgot_password():
    """Generate password reset token."""
    data = request.get_json() or {}
    username = data.get('username', '')
    
    token = user_model.generate_reset_token(username)
    
    if not token:
        return jsonify({'ok': False, 'error': 'Username not found.'}), 400
    
    return jsonify({'ok': True, 'token': token})


@auth_bp.route('/reset', methods=['POST'])
def reset_password():
    """Reset password using token."""
    data = request.get_json() or {}
    username = data.get('username', '')
    token = data.get('token', '')
    password = data.get('password', '')
    
    success, message = user_model.reset_password(username, token, password)
    
    if not success:
        return jsonify({'ok': False, 'error': message}), 400
    
    return jsonify({'ok': True, 'message': message})
