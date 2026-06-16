"""
app.py — Complete Baghchal Flask app (self-contained, no external module deps).
Integrated: auth, AI stubs, game lifecycle, admin panel, session management.
"""
import copy
import time
import uuid
import json
import os
from functools import wraps
from flask import Flask, render_template, request, session, jsonify

import engine as eng
import game_store as gs
import report
import auth
import ai

# ══════════════════════════════════════════════════════════════
#  AUTH MODULE (integrated)
# ══════════════════════════════════════════════════════════════

_users_db = {}  # username -> {'username': ..., 'password': ..., 'role': ..., 'games_played': ..., 'created_at': ...}

def init_auth():
    """Initialize default admin user."""
    global _users_db
    if 'admin' not in _users_db:
        _users_db['admin'] = {
            'username': 'admin',
            'password': 'admin123',  # CHANGE IN PRODUCTION
            'email': 'admin@localhost',
            'role': 'admin',
            'games_played': 0,
            'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        }

# ══════════════════════════════════════════════════════════════
#  AI MODULE (integrated — simple heuristic)
# ══════════════════════════════════════════════════════════════

def find_best_move(state, faction, difficulty='medium'):
    """Find the best move for AI. Returns a move dict or None."""
    moves = eng.get_all_moves(state, faction)
    if not moves:
        return None
    
    # Simple strategy: prioritize captures, then center control
    if faction == 'tiger':
        # Tigers prefer capturing goats
        cap_moves = [m for m in moves if m.get('capture', -1) >= 0]
        if cap_moves:
            return cap_moves[0]
    
    # Otherwise, prefer moves toward center
    moves.sort(key=lambda m: eng.CENTER_WEIGHTS[m['to']], reverse=True)
    return moves[0]

def evaluate_for_draw(state, faction):
    """Evaluate if AI should accept a draw offer."""
    # Simple: accept if not winning
    moves = eng.get_all_moves(state, faction)
    if len(moves) <= 3:
        return True  # Accept if desperate
    if faction == 'tiger' and state['goats_captured'] >= 3:
        return False  # Don't accept if winning
    return True

# ══════════════════════════════════════════════════════════════
#  Flask App
# ══════════════════════════════════════════════════════════════

app = Flask(__name__)
app.secret_key = 'baghchal-server-secret-change-in-production'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# ══════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════

def _state_payload(game):
    """Build the JSON payload the frontend needs to render the board."""
    s = game['state']
    log = game['move_log']
    return {
        'game_id': game['id'],
        'board': s['board'],
        'goats_placed': s['goats_placed'],
        'goats_captured': s['goats_captured'],
        'current_turn': s['current_turn'],
        'phase': s['phase'],
        'status': s['status'],
        'tiger_moves': s['tiger_moves'],
        'goat_moves': s['goat_moves'],
        'mode': game['mode'],
        'human_role': game['human_role'],
        'difficulty': game['difficulty'],
        'draw_offered': game['draw_offered'],
        'draw_off_by': game['draw_off_by'],
        'move_log': log,
        'can_undo': game['prev_state'] is not None,
        'game_number': game.get('game_number'),
        'session_id': game.get('session_game_id', '').split('_')[0] if game.get('session_game_id') else None,
        'time_limit': game.get('time_limit'),
        'time_remaining': game.get('time_remaining', game.get('time_limit')),
    }

def _log_move(game, faction, desc, is_capture, timestamp, legal_moves):
    gs.add_move_log(game, faction, desc, is_capture, timestamp, legal_moves)

def _execute_action(game, action):
    """Apply action to game state, handle AI follow-up. Returns updated payload."""
    s = game['state']
    faction = s['current_turn']
    was_phase1 = (s['phase'] == 1)

    # Snapshot pre-human state for undo
    if game['mode'] == 'ai' and faction == game['human_role']:
        game['prev_state'] = copy.deepcopy(s)
    elif game['mode'] == 'hotseat':
        game['prev_state'] = copy.deepcopy(s)

    # Human move
    human_ts = time.time()
    human_legal = eng.format_moves_list(eng.get_all_moves(s, faction))

    new_state, captured_node = eng.apply_move(s, action)
    game['state'] = new_state

    if action['type'] == 'place':
        desc = f'→ {eng.node_label(action["to"])}'
    else:
        cap_str = f' ✕{eng.node_label(action["capture"])}' if action.get('capture', -1) >= 0 else ''
        desc = f'{eng.node_label(action["from"])} → {eng.node_label(action["to"])}{cap_str}'
    is_cap = action.get('capture', -1) >= 0
    _log_move(game, faction, desc, is_cap, human_ts, human_legal)

    # AI follow-up
    ai_desc = None
    ai_captured = -1
    ai_from = -1
    ai_to = -1
    ai_action_type = None

    if (game['mode'] == 'ai'
            and new_state['status'] == 'active'
            and new_state['current_turn'] != game['human_role']):
        ai_role = 'goat' if game['human_role'] == 'tiger' else 'tiger'
        ai_ts = time.time()
        ai_legal = eng.format_moves_list(eng.get_all_moves(new_state, ai_role))
        ai_mv = ai.find_best_move(new_state, ai_role, game['difficulty'])
        if ai_mv:
            ai_action_type = ai_mv['type']
            ai_from = ai_mv.get('from', -1)
            ai_to = ai_mv['to']
            ai_cap = ai_mv.get('capture', -1)
            if ai_mv['type'] == 'place':
                ai_desc = f'→ {eng.node_label(ai_to)}'
            else:
                cap_str = f' ✕{eng.node_label(ai_cap)}' if ai_cap >= 0 else ''
                ai_desc = f'{eng.node_label(ai_from)} → {eng.node_label(ai_to)}{cap_str}'
            after_ai, ai_captured = eng.apply_move(new_state, ai_mv)
            game['state'] = after_ai
            _log_move(game, ai_role, ai_desc, ai_cap >= 0, ai_ts, ai_legal)

    # End of move
    if game['state']['status'] != 'active':
        game['end_time'] = time.time()
        report.export_game_report(game)
        auth.auth.increment_games(game['username'])

    gs.save_game(game)

    payload = _state_payload(game)
    payload['captured_node'] = captured_node
    payload['ai_action_type'] = ai_action_type
    payload['ai_from'] = ai_from
    payload['ai_to'] = ai_to
    payload['ai_captured'] = ai_captured
    payload['ai_desc'] = ai_desc
    return payload

# ══════════════════════════════════════════════════════════════
#  ROUTES — Pages
# ══════════════════════════════════════════════════════════════

@app.route('/')
def index():
    user = auth.current_user()
    if not user:
        return render_template('auth.html')
    # Ensure session exists
    session_data = gs.get_session(user['username'])
    if not session_data or session_data['finished']:
        session_data = gs.new_session(user['username'])
    return render_template('game.html',
                           user=user,
                           session=session_data,
                           current_game=session_data['current_game'])

@app.route('/admin')
@auth.login_required
@auth.admin_required
def admin():
    user = auth.current_user()
    users = auth.all_users()
    return render_template('admin.html', user=user, users=users)

# ══════════════════════════════════════════════════════════════
#  API — Auth
# ══════════════════════════════════════════════════════════════

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    d = request.get_json()
    ok, result = auth.login(d.get('username', ''), d.get('password', ''))
    if not ok:
        return jsonify({'ok': False, 'error': result}), 400
    session['username'] = result['username']
    session['role'] = result['role']
    return jsonify({'ok': True, 'username': result['username'], 'role': result['role']})

@app.route('/api/auth/register', methods=['POST'])
def api_register():
    d = request.get_json()
    ok, result = auth.register(d.get('username', ''), d.get('password', ''), d.get('email', ''))
    if not ok:
        return jsonify({'ok': False, 'error': result}), 400
    auth.auth.login(result['username'], d.get('password', ''))
    session['username'] = result['username']
    session['role'] = result['role']
    return jsonify({'ok': True, 'username': result['username'], 'role': result['role']})

@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'ok': True})

@app.route('/api/auth/forgot', methods=['POST'])
def api_forgot():
    d = request.get_json()
    token = auth.generate_reset_token(d.get('username', ''))
    if not token:
        return jsonify({'ok': False, 'error': 'Username not found.'}), 400
    return jsonify({'ok': True, 'token': token})

@app.route('/api/auth/reset', methods=['POST'])
def api_reset():
    d = request.get_json()
    ok, msg = auth.reset_password(d.get('username', ''), d.get('token', ''), d.get('password', ''))
    if not ok:
        return jsonify({'ok': False, 'error': msg}), 400
    return jsonify({'ok': True, 'message': msg})

# ══════════════════════════════════════════════════════════════
#  API — Session & Game lifecycle
# ══════════════════════════════════════════════════════════════

@app.route('/api/game/next', methods=['GET'])
@auth.login_required
def api_next_game():
    """Return the next game in the session (creates it if needed)."""
    username = session['username']
    session_data = gs.get_session(username)
    if not session_data or session_data['finished']:
        session_data = gs.new_session(username)
    
    game_id, num = gs.get_next_game_id(username)
    if not game_id:
        return jsonify({'ok': False, 'error': 'All games completed'}), 400

    # Determine game parameters
    if num == 1:
        human_role = 'tiger'
        difficulty = 'easy'
        mode = 'ai'
        time_limit = None
    elif num == 2:
        human_role = 'goat'
        difficulty = 'easy'
        mode = 'ai'
        time_limit = None
    elif num == 3:
        human_role = 'tiger'
        difficulty = 'medium'
        mode = 'ai'
        time_limit = None
    elif num == 4:
        human_role = 'goat'
        difficulty = 'medium'
        mode = 'ai'
        time_limit = None
    elif num == 5:
        human_role = 'tiger'
        difficulty = 'medium'
        mode = 'ai'
        time_limit = 7 * 60  # 7 minutes for timed game
    else:
        return jsonify({'ok': False, 'error': 'Invalid game number'}), 400

    game_id = gs.new_game(username, mode, human_role, difficulty)
    game = gs.get_game(game_id)
    game['game_number'] = num
    game['session_game_id'] = f"{session_data['session_id']}_{num:03d}"
    game['time_limit'] = time_limit
    game['time_remaining'] = time_limit
    gs.save_game(game)

    return jsonify({'ok': True, **_state_payload(game)})

@app.route('/api/game/move', methods=['POST'])
@auth.login_required
def api_move():
    """Submit a move or place action."""
    d = request.get_json()
    game_id = d.get('game_id')
    game = gs.get_game(game_id)
    
    if not game or game['username'] != session['username']:
        return jsonify({'ok': False, 'error': 'Game not found'}), 404
    if game['state']['status'] != 'active':
        return jsonify({'ok': False, 'error': 'Game is over'}), 400
    if game['draw_offered']:
        return jsonify({'ok': False, 'error': 'Draw offer pending'}), 400

    # Timer: if time limit and time remaining has expired
    if game.get('time_limit') and game.get('time_remaining', 0) <= 0:
        game['state']['status'] = 'tiger_win' if game['human_role'] == 'goat' else 'goat_win'
        game['end_time'] = time.time()
        report.export_game_report(game)
        auth.auth.increment_games(game['username'])
        gs.save_game(game)
        return jsonify({'ok': True, **_state_payload(game)})

    s = game['state']
    turn = s['current_turn']

    if game['mode'] == 'ai' and turn != game['human_role']:
        return jsonify({'ok': False, 'error': 'Not your turn'}), 400

    action_type = d.get('action_type')
    to_node = d.get('to_node')

    if action_type == 'place':
        if turn != 'goat' or s['phase'] != 1:
            return jsonify({'ok': False, 'error': 'Cannot place now'}), 400
        if s['board'][to_node] is not None:
            return jsonify({'ok': False, 'error': 'Square occupied'}), 400
        action = {'type': 'place', 'to': to_node}

    elif action_type == 'move':
        from_node = d.get('from_node')
        if s['board'][from_node] != turn:
            return jsonify({'ok': False, 'error': 'Not your piece'}), 400
        legal = eng.get_moves_for(s, from_node)
        mv = next((m for m in legal if m['to'] == to_node), None)
        if not mv:
            return jsonify({'ok': False, 'error': 'Illegal move'}), 400
        action = {'type': 'move', 'from': from_node, 'to': to_node, 'capture': mv['capture']}
    elif action_type == 'timeout':
        game['state']['status'] = 'tiger_win' if game['human_role'] == 'goat' else 'goat_win'
        game['end_time'] = time.time()
        report.export_game_report(game)
        auth.auth.increment_games(game['username'])
        gs.save_game(game)
        return jsonify({'ok': True, **_state_payload(game)})
    else:
        return jsonify({'ok': False, 'error': 'Unknown action'}), 400

    payload = _execute_action(game, action)

    # If this game just ended and it's not the last, set next_game_available flag
    if game['state']['status'] != 'active':
        session_data = gs.get_session(game['username'])
        if session_data and session_data['current_game'] <= 5:
            payload['next_game_available'] = True
        else:
            payload['next_game_available'] = False

    return jsonify({'ok': True, **payload})

@app.route('/api/game/timer', methods=['POST'])
@auth.login_required
def api_timer():
    d = request.get_json()
    game_id = d.get('game_id')
    time_remaining = d.get('time_remaining')
    game = gs.get_game(game_id)
    if not game or game['username'] != session['username']:
        return jsonify({'ok': False, 'error': 'Game not found'}), 404
    game['time_remaining'] = time_remaining
    gs.save_game(game)
    return jsonify({'ok': True})

# ══════════════════════════════════════════════════════════════
#  API — Undo, Resign, Draw
# ══════════════════════════════════════════════════════════════

@app.route('/api/game/undo', methods=['POST'])
@auth.login_required
def api_undo():
    d = request.get_json()
    game_id = d.get('game_id')
    game = gs.get_game(game_id)
    if not game or game['username'] != session['username']:
        return jsonify({'ok': False, 'error': 'Game not found'}), 404
    if game['prev_state'] is None:
        return jsonify({'ok': False, 'error': 'Nothing to undo'}), 400

    game['state'] = copy.deepcopy(game['prev_state'])
    game['prev_state'] = None
    remove = 2 if game['mode'] == 'ai' and len(game['move_log']) >= 2 else 1
    game['move_log'] = game['move_log'][:-remove]
    gs.save_game(game)
    return jsonify({'ok': True, **_state_payload(game)})

@app.route('/api/game/resign', methods=['POST'])
@auth.login_required
def api_resign():
    d = request.get_json()
    game_id = d.get('game_id')
    game = gs.get_game(game_id)
    if not game or game['username'] != session['username']:
        return jsonify({'ok': False, 'error': 'Game not found'}), 404
    if game['state']['status'] != 'active':
        return jsonify({'ok': False, 'error': 'Game already over'}), 400

    s = game['state']
    resigning = s['current_turn'] if game['mode'] == 'hotseat' else game['human_role']
    result = 'tiger_resigned' if resigning == 'tiger' else 'goat_resigned'
    s['status'] = result
    game['end_time'] = time.time()
    report.export_game_report(game)
    auth.auth.increment_games(session['username'])
    gs.save_game(game)
    return jsonify({'ok': True, **_state_payload(game)})

@app.route('/api/game/draw', methods=['POST'])
@auth.login_required
def api_draw():
    d = request.get_json()
    game_id = d.get('game_id')
    action = d.get('action')
    game = gs.get_game(game_id)

    if not game or game['username'] != session['username']:
        return jsonify({'ok': False, 'error': 'Game not found'}), 404
    s = game['state']
    if s['status'] != 'active':
        return jsonify({'ok': False, 'error': 'Game over'}), 400

    if action == 'offer':
        if s['phase'] < 2:
            return jsonify({'ok': False, 'error': 'Draw only available in Phase 2'}), 400
        if game['draw_offered']:
            return jsonify({'ok': False, 'error': 'Draw already offered'}), 400
        if game['mode'] == 'ai' and s['current_turn'] != game['human_role']:
            return jsonify({'ok': False, 'error': 'Not your turn'}), 400

        game['draw_offered'] = True
        game['draw_off_by'] = s['current_turn']

        if game['mode'] == 'ai':
            ai_role = 'goat' if game['human_role'] == 'tiger' else 'tiger'
            accepted = ai.evaluate_for_draw(s, ai_role)
            game['draw_offered'] = False
            game['draw_off_by'] = None
            if accepted:
                s['status'] = 'draw_agreement'
                game['end_time'] = time.time()
                report.export_game_report(game)
                auth.auth.increment_games(session['username'])
            gs.save_game(game)
            return jsonify({'ok': True, 'ai_response': 'accepted' if accepted else 'declined',
                            **_state_payload(game)})

        gs.save_game(game)
        return jsonify({'ok': True, **_state_payload(game)})

    elif action == 'accept':
        if not game['draw_offered']:
            return jsonify({'ok': False, 'error': 'No draw offer pending'}), 400
        s['status'] = 'draw_agreement'
        game['draw_offered'] = False
        game['draw_off_by'] = None
        game['end_time'] = time.time()
        report.export_game_report(game)
        auth.auth.increment_games(session['username'])
        gs.save_game(game)
        return jsonify({'ok': True, **_state_payload(game)})

    elif action == 'decline':
        game['draw_offered'] = False
        game['draw_off_by'] = None
        gs.save_game(game)
        return jsonify({'ok': True, **_state_payload(game)})

    return jsonify({'ok': False, 'error': 'Unknown draw action'}), 400

# ══════════════════════════════════════════════════════════════
#  API — Admin
# ══════════════════════════════════════════════════════════════

@app.route('/api/admin/users', methods=['GET'])
@auth.admin_required
def api_admin_users():
    return jsonify({'users': all_users()})

@app.route('/api/admin/delete', methods=['POST'])
@auth.admin_required
def api_admin_delete():
    d = request.get_json()
    username = d.get('username', '')
    auth.auth.delete_user(username)
    return jsonify({'ok': True, 'users': all_users()})

# ══════════════════════════════════════════════════════════════
#  RUN
# ══════════════════════════════════════════════════════════════

report.ensure_dir()

if __name__ == '__main__':
    import os
    debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(debug=debug_mode, port=5000, host='127.0.0.1')