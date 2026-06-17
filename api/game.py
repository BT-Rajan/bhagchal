"""
Game API routes.

Handles game lifecycle, moves, undo, resign, draw offers.
"""
import copy
import time
from flask import Blueprint, request, jsonify, session

from models.user import user_model
from models.game import session_store, game_store
from services.engine import GameEngine, format_moves_list, node_label
from services.ai import ai_service
from services.report import report_service
from config import Config

game_bp = Blueprint('game', __name__, url_prefix='/api/game')


def _state_payload(game):
    """Build JSON payload for game state."""
    s = game['state']
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
        'move_log': game['move_log'],
        'can_undo': game['prev_state'] is not None,
        'game_number': game.get('game_number'),
        'session_id': (
            game.get('session_game_id', '').split('_')[0] 
            if game.get('session_game_id') else None
        ),
        'time_limit': game.get('time_limit'),
        'time_remaining': game.get('time_remaining', game.get('time_limit'))
    }


def _execute_action(game, action):
    """Apply action and handle AI follow-up."""
    s = game['state']
    faction = s['current_turn']
    
    # Snapshot for undo
    if game['mode'] == 'ai' and faction == game['human_role']:
        game['prev_state'] = copy.deepcopy(s)
    elif game['mode'] == 'hotseat':
        game['prev_state'] = copy.deepcopy(s)
    
    # Apply human move
    human_ts = time.time()
    human_legal = format_moves_list(GameEngine.get_all_moves(s, faction))
    
    new_state, captured_node = GameEngine.apply_move(s, action)
    game['state'] = new_state
    
    # Log move
    if action['type'] == 'place':
        desc = f'→ {node_label(action["to"])}'
    else:
        cap_str = f' ✕{node_label(action["capture"])}' if action.get('capture', -1) >= 0 else ''
        desc = f'{node_label(action["from"])} → {node_label(action["to"])}{cap_str}'
    
    is_cap = action.get('capture', -1) >= 0
    game_store.add_move_log(game, faction, desc, is_cap, human_ts, human_legal)
    
    # AI follow-up
    ai_desc = ai_from = ai_to = ai_action_type = None
    ai_captured = -1
    
    if (game['mode'] == 'ai' and 
        new_state['status'] == 'active' and 
        new_state['current_turn'] != game['human_role']):
        
        ai_role = 'goat' if game['human_role'] == 'tiger' else 'tiger'
        ai_ts = time.time()
        ai_legal = format_moves_list(GameEngine.get_all_moves(new_state, ai_role))
        ai_mv = ai_service.find_best_move(new_state, ai_role, game['difficulty'])
        
        if ai_mv:
            ai_action_type = ai_mv['type']
            ai_from = ai_mv.get('from', -1)
            ai_to = ai_mv['to']
            ai_cap = ai_mv.get('capture', -1)
            
            if ai_mv['type'] == 'place':
                ai_desc = f'→ {node_label(ai_to)}'
            else:
                cap_str = f' ✕{node_label(ai_cap)}' if ai_cap >= 0 else ''
                ai_desc = f'{node_label(ai_from)} → {node_label(ai_to)}{cap_str}'
            
            after_ai, ai_captured = GameEngine.apply_move(new_state, ai_mv)
            game['state'] = after_ai
            game_store.add_move_log(game, ai_role, ai_desc, ai_cap >= 0, ai_ts, ai_legal)
    
    # Handle game end
    if game['state']['status'] != 'active':
        game['end_time'] = time.time()
        report_service.export_game_report(game)
        user_model.increment_games(game['username'])
    
    game_store.save_game(game)
    
    payload = _state_payload(game)
    payload['captured_node'] = captured_node
    payload['ai_action_type'] = ai_action_type
    payload['ai_from'] = ai_from
    payload['ai_to'] = ai_to
    payload['ai_captured'] = ai_captured
    payload['ai_desc'] = ai_desc
    
    return payload


@game_bp.route('/next', methods=['GET'])
def next_game():
    """Get/create the next game in the session."""
    username = session.get('username')
    if not username:
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    
    sess = session_store.get_session(username)
    if not sess or sess['finished']:
        sess = session_store.new_session(username)
    
    game_id, num = session_store.get_next_game_id(username)
    if not game_id:
        return jsonify({'ok': False, 'error': 'All games completed'}), 400
    
    # Determine game parameters based on game number
    params = {
        1: ('tiger', 'easy'),
        2: ('goat', 'easy'),
        3: ('tiger', 'medium'),
        4: ('goat', 'medium'),
        5: ('tiger', 'medium')
    }
    
    if num not in params:
        return jsonify({'ok': False, 'error': 'Invalid game number'}), 400
    
    human_role, difficulty = params[num]
    time_limit = Config.TIMED_GAME_LIMIT if num == Config.TIMED_GAME_NUMBER else None
    
    game_id = game_store.new_game(username, 'ai', human_role, difficulty)
    game = game_store.get_game(game_id)
    game['game_number'] = num
    game['session_game_id'] = f"{sess['session_id']}_{num:03d}"
    game['time_limit'] = time_limit
    game['time_remaining'] = time_limit
    game_store.save_game(game)
    
    return jsonify({'ok': True, **_state_payload(game)})


@game_bp.route('/move', methods=['POST'])
def make_move():
    """Submit a move or place action."""
    username = session.get('username')
    if not username:
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    
    data = request.get_json() or {}
    game_id = data.get('game_id')
    game = game_store.get_game(game_id)
    
    if not game or game['username'] != username:
        return jsonify({'ok': False, 'error': 'Game not found'}), 404
    if game['state']['status'] != 'active':
        return jsonify({'ok': False, 'error': 'Game is over'}), 400
    if game['draw_offered']:
        return jsonify({'ok': False, 'error': 'Draw offer pending'}), 400
    
    # Check timer
    if game.get('time_limit') and game.get('time_remaining', 0) <= 0:
        game['state']['status'] = (
            'tiger_win' if game['human_role'] == 'goat' else 'goat_win'
        )
        game['end_time'] = time.time()
        report_service.export_game_report(game)
        user_model.increment_games(username)
        game_store.save_game(game)
        return jsonify({'ok': True, **_state_payload(game)})
    
    s = game['state']
    turn = s['current_turn']
    
    if game['mode'] == 'ai' and turn != game['human_role']:
        return jsonify({'ok': False, 'error': 'Not your turn'}), 400
    
    action_type = data.get('action_type')
    to_node = data.get('to_node')
    
    if action_type == 'timeout':
        game['state']['status'] = (
            'tiger_win' if game['human_role'] == 'goat' else 'goat_win'
        )
        game['end_time'] = time.time()
        report_service.export_game_report(game)
        user_model.increment_games(username)
        game_store.save_game(game)
        return jsonify({'ok': True, **_state_payload(game)})
    
    if action_type == 'place':
        if turn != 'goat' or s['phase'] != 1:
            return jsonify({'ok': False, 'error': 'Cannot place now'}), 400
        if s['board'][to_node] is not None:
            return jsonify({'ok': False, 'error': 'Square occupied'}), 400
        action = {'type': 'place', 'to': to_node}
    
    elif action_type == 'move':
        from_node = data.get('from_node')
        if s['board'][from_node] != turn:
            return jsonify({'ok': False, 'error': 'Not your piece'}), 400
        
        legal = GameEngine.get_moves_for(s, from_node)
        mv = next((m for m in legal if m['to'] == to_node), None)
        if not mv:
            return jsonify({'ok': False, 'error': 'Illegal move'}), 400
        
        action = {
            'type': 'move', 
            'from': from_node, 
            'to': to_node, 
            'capture': mv['capture']
        }
    else:
        return jsonify({'ok': False, 'error': 'Unknown action'}), 400
    
    payload = _execute_action(game, action)
    
    # Check if next game is available
    if game['state']['status'] != 'active':
        sess = session_store.get_session(username)
        payload['next_game_available'] = sess and sess['current_game'] <= 5
    
    return jsonify({'ok': True, **payload})


@game_bp.route('/timer', methods=['POST'])
def update_timer():
    """Update remaining time for timed games."""
    username = session.get('username')
    if not username:
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    
    data = request.get_json() or {}
    game_id = data.get('game_id')
    time_remaining = data.get('time_remaining')
    
    game = game_store.get_game(game_id)
    if not game or game['username'] != username:
        return jsonify({'ok': False, 'error': 'Game not found'}), 404
    
    game['time_remaining'] = time_remaining
    game_store.save_game(game)
    
    return jsonify({'ok': True})


@game_bp.route('/undo', methods=['POST'])
def undo_move():
    """Undo the last move(s)."""
    username = session.get('username')
    if not username:
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    
    data = request.get_json() or {}
    game_id = data.get('game_id')
    game = game_store.get_game(game_id)
    
    if not game or game['username'] != username:
        return jsonify({'ok': False, 'error': 'Game not found'}), 404
    if game['prev_state'] is None:
        return jsonify({'ok': False, 'error': 'Nothing to undo'}), 400
    
    game['state'] = copy.deepcopy(game['prev_state'])
    game['prev_state'] = None
    
    # Remove moves from log
    remove_count = 2 if game['mode'] == 'ai' and len(game['move_log']) >= 2 else 1
    game['move_log'] = game['move_log'][:-remove_count]
    
    game_store.save_game(game)
    
    return jsonify({'ok': True, **_state_payload(game)})


@game_bp.route('/resign', methods=['POST'])
def resign():
    """Forfeit the current game."""
    username = session.get('username')
    if not username:
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    
    data = request.get_json() or {}
    game_id = data.get('game_id')
    game = game_store.get_game(game_id)
    
    if not game or game['username'] != username:
        return jsonify({'ok': False, 'error': 'Game not found'}), 404
    if game['state']['status'] != 'active':
        return jsonify({'ok': False, 'error': 'Game already over'}), 400
    
    s = game['state']
    resigning = s['current_turn'] if game['mode'] == 'hotseat' else game['human_role']
    s['status'] = 'tiger_resigned' if resigning == 'tiger' else 'goat_resigned'
    
    game['end_time'] = time.time()
    report_service.export_game_report(game)
    user_model.increment_games(username)
    game_store.save_game(game)
    
    payload = _state_payload(game)
    sess = session_store.get_session(username)
    payload['next_game_available'] = bool(sess and sess['current_game'] <= 5)
    return jsonify({'ok': True, **payload})


@game_bp.route('/draw', methods=['POST'])
def draw_offer():
    """Offer, accept, or decline a draw."""
    username = session.get('username')
    if not username:
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    
    data = request.get_json() or {}
    game_id = data.get('game_id')
    action = data.get('action')  # 'offer', 'accept', 'decline'
    
    game = game_store.get_game(game_id)
    if not game or game['username'] != username:
        return jsonify({'ok': False, 'error': 'Game not found'}), 404
    if game['state']['status'] != 'active':
        return jsonify({'ok': False, 'error': 'Game already over'}), 400
    
    if action == 'offer':
        if game['state']['phase'] < 2:
            return jsonify({'ok': False, 'error': 'Draw only available in Phase 2'}), 400
        if game['draw_offered']:
            return jsonify({'ok': False, 'error': 'Draw already offered'}), 400
        if game['mode'] == 'ai' and game['state']['current_turn'] != game['human_role']:
            return jsonify({'ok': False, 'error': 'Not your turn'}), 400
        
        game['draw_offered'] = True
        game['draw_off_by'] = game['state']['current_turn']
        
        ai_response = None
        if game['mode'] == 'ai':
            # No human opponent to click "Accept" - the AI must decide right away.
            ai_role = 'goat' if game['human_role'] == 'tiger' else 'tiger'
            accepted = ai_service.should_accept_draw(game['state'], ai_role)
            game['draw_offered'] = False
            game['draw_off_by'] = None
            ai_response = 'accepted' if accepted else 'declined'
            if accepted:
                game['state']['status'] = 'draw_agreement'
                game['end_time'] = time.time()
                report_service.export_game_report(game)
                user_model.increment_games(username)
        
        game_store.save_game(game)
        payload = _state_payload(game)
        if ai_response:
            payload['ai_response'] = ai_response
        if game['state']['status'] != 'active':
            sess = session_store.get_session(username)
            payload['next_game_available'] = bool(sess and sess['current_game'] <= 5)
        return jsonify({'ok': True, **payload})
    
    elif action == 'accept':
        if not game['draw_offered']:
            return jsonify({'ok': False, 'error': 'No draw offer to accept'}), 400
        
        # Check if AI should accept
        if game['mode'] == 'ai':
            ai_role = 'goat' if game['human_role'] == 'tiger' else 'tiger'
            if not ai_service.should_accept_draw(game['state'], ai_role):
                game['draw_offered'] = False
                game['draw_off_by'] = None
                game_store.save_game(game)
                return jsonify({
                    'ok': True, 
                    'draw_accepted': False,
                    'message': 'AI declined the draw offer',
                    **_state_payload(game)
                })
        
        game['state']['status'] = 'draw_agreement'
        game['draw_offered'] = False
        game['draw_off_by'] = None
        game['end_time'] = time.time()
        report_service.export_game_report(game)
        user_model.increment_games(username)
        game_store.save_game(game)
        
        payload = _state_payload(game)
        sess = session_store.get_session(username)
        payload['next_game_available'] = bool(sess and sess['current_game'] <= 5)
        return jsonify({'ok': True, **payload})
    
    elif action == 'decline':
        game['draw_offered'] = False
        game['draw_off_by'] = None
        game_store.save_game(game)
        return jsonify({'ok': True, **_state_payload(game)})
    
    else:
        return jsonify({'ok': False, 'error': 'Unknown draw action'}), 400
