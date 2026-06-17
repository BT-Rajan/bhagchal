"""
Bagh Chal - Tiger and Goat Board Game

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
from flask import Flask, render_template


def create_app(config_name='default'):
    """Application factory for Bagh Chal."""
    from config import config
    from api import auth_bp, game_bp
    from utils.decorators import current_user
    from models.game import session_store
    
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(game_bp)
    
    # Page routes
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
            current_game=sess['current_game']
        )
    
    @app.route('/admin')
    @app.route('/admin/')
    def admin():
        from models.user import user_model
        
        # Check admin access
        user = current_user()
        if not user:
            return render_template('auth.html')
        if user['role'] != 'admin':
            return 'Admin access required', 403
        
        users = user_model.all_users()
        return render_template('admin.html', user=user, users=users)
    
    # Admin API routes (inline for simplicity)
    @app.route('/api/admin/users', methods=['GET'])
    def api_admin_users():
        from models.user import user_model
        from flask import jsonify
        
        # Check auth inline
        from utils.decorators import current_user as get_current
        user = get_current()
        if not user:
            return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
        if user['role'] != 'admin':
            return jsonify({'ok': False, 'error': 'Admin access required'}), 403
        
        users = user_model.all_users()
        return jsonify({'ok': True, 'users': users})
    
    @app.route('/api/admin/delete', methods=['POST'])
    def api_admin_delete():
        from models.user import user_model
        from flask import request, jsonify
        
        # Check auth inline
        from utils.decorators import current_user as get_current
        user = get_current()
        if not user:
            return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
        if user['role'] != 'admin':
            return jsonify({'ok': False, 'error': 'Admin access required'}), 403
        
        data = request.get_json() or {}
        username = data.get('username', '')
        
        if not username:
            return jsonify({'ok': False, 'error': 'Username required'}), 400
        
        user_model.delete_user(username)
        return jsonify({'ok': True})
    
    return app


# Create default app instance for direct running
app = create_app()


if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(host='127.0.0.1', port=5000, debug=debug_mode)
