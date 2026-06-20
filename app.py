import os, time
from flask import Flask, jsonify, render_template, request, session

from api import auth_bp, game_bp, admin_bp, sponsor_bp
from config import config
from models.game import session_store
from models.user import user_model
from utils.decorators import admin_required, sponsor_required, current_user


def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    _boot_epoch = int(time.time())

    @app.before_request
    def _validate_session():
        if 'username' in session:
            if session.get('boot_epoch', 0) < _boot_epoch:
                session.clear()

    from models.db import init_db
    init_db()

    app.register_blueprint(auth_bp)
    app.register_blueprint(game_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(sponsor_bp)

    @app.after_request
    def no_cache(response):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma']  = 'no-cache'
        response.headers['Expires'] = '0'
        return response

    # ── Page routes ───────────────────────────────────────────────────────

    @app.route('/')
    def index():
        user = current_user()
        if not user:
            return render_template('auth.html')
        if user['suspended']:
            session.clear()
            return render_template('auth.html', error='Account suspended.')
        # Sponsors and admins go to their own dashboards
        if user['role'] == 'sponsor':
            return render_template('sponsor.html', user=user)
        if user['role'] == 'admin':
            return render_template('admin.html', user=user,
                                   users=user_model.all_users())
        # Regular user — game session
        sess = session_store.get_session(user['username'])
        if not sess or sess['finished']:
            sess = session_store.new_session(user['username'])
        return render_template('game.html', user=user, session=sess,
                               current_game=sess['current_game'])

    @app.route('/admin')
    @app.route('/admin/')
    def admin_page():
        user = current_user()
        if not user:
            return render_template('auth.html')
        if user['role'] != 'admin':
            return 'Admin access required', 403
        return render_template('admin.html', user=user,
                               users=user_model.all_users())

    @app.route('/sponsor')
    def sponsor_page():
        user = current_user()
        if not user:
            return render_template('auth.html')
        if user['role'] not in ('admin','sponsor'):
            return 'Sponsor access required', 403
        return render_template('sponsor.html', user=user)

    @app.route('/register')
    def invite_register():
        token = request.args.get('invite','')
        return render_template('auth.html', invite_token=token)

    # ── Legacy admin API (kept for backward compat) ───────────────────────

    @app.route('/api/admin/users', methods=['GET'])
    @admin_required
    def api_admin_users():
        return jsonify({'ok': True, 'users': user_model.all_users()})

    @app.route('/api/admin/delete', methods=['POST'])
    @admin_required
    def api_admin_delete():
        data = request.get_json() or {}
        username = data.get('username','').strip()
        if not username:
            return jsonify({'ok': False, 'error': 'Username required'}), 400
        if not user_model.delete_user(username):
            return jsonify({'ok': False, 'error': 'User not found or cannot be deleted'}), 404
        return jsonify({'ok': True})

    return app


app = create_app()

if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG','0') == '1'
    app.run(host='127.0.0.1', port=5000, debug=debug_mode)
