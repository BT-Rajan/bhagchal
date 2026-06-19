"""
BEINT — Behavioral Intelligence Platform

A Flask-based server-authoritative implementation of the traditional Nepali board game.
All game logic, AI, and state management run on the server.

Usage:
    python3 app.py

Or:
    from app import create_app
    app = create_app()
    app.run()
"""

import os

from flask import Flask, jsonify, render_template, request

from api import auth_bp, game_bp
from config import config
from models.game import session_store
from models.user import user_model
from utils.decorators import admin_required, current_user


def create_app(config_name='default'):
    """Application factory for BEINT."""
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # ── Blueprints ────────────────────────────────────────────────────────
    app.register_blueprint(auth_bp)
    app.register_blueprint(game_bp)

    # ── No-cache on all responses (prevents stale login/game screens) ─────

    @app.after_request
    def no_cache(response):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response

    # ── Page routes ───────────────────────────────────────────────────────

    @app.route('/')
    def index():
        user = current_user()
        if not user:
            return render_template('auth.html')

        username = user['username']
        sess = session_store.get_session(username)
        if not sess or sess['finished']:
            sess = session_store.new_session(username)

        return render_template(
            'game.html',
            user=user,
            session=sess,
            current_game=sess['current_game'],
        )

    @app.route('/admin')
    @app.route('/admin/')
    def admin():
        user = current_user()
        if not user:
            return render_template('auth.html')
        if user['role'] != 'admin':
            return 'Admin access required', 403

        users = user_model.all_users()
        return render_template('admin.html', user=user, users=users)

    # ── Admin API routes ──────────────────────────────────────────────────

    @app.route('/api/admin/users', methods=['GET'])
    @admin_required
    def api_admin_users():
        users = user_model.all_users()
        return jsonify({'ok': True, 'users': users})

    @app.route('/api/admin/delete', methods=['POST'])
    @admin_required
    def api_admin_delete():
        data = request.get_json() or {}
        username = data.get('username', '').strip()

        if not username:
            return jsonify({'ok': False, 'error': 'Username required'}), 400

        deleted = user_model.delete_user(username)
        if not deleted:
            return jsonify({'ok': False, 'error': 'User not found or cannot be deleted'}), 404

        return jsonify({'ok': True})

    return app


# Create default app instance for direct running
app = create_app()


if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(host='127.0.0.1', port=5000, debug=debug_mode)
