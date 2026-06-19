"""
Game API routes.

Handles game lifecycle, moves, undo, resign, draw offers.
"""
import copy
import time
from flask import Blueprint, jsonify, request, session

from config import Config
from models.game import game_store, session_store
from models.user import user_model
from services.ai import ai_service
from services.engine import GameEngine, format_moves_list, node_label
from services.report import report_service

game_bp = Blueprint('game', __name__, url_prefix='/api/game')

_WIN_STATUSES = frozenset({'tiger_win', 'goat_win', 'tiger_resigned', 'goat_resigned',
                            'draw_agreement', 'draw_no_moves', 'draw_repetition'})


def _state_payload(game: dict) -> dict:
    """Build JSON-serialisable payload for the current game state."""
    s = game['state']
    return {
        'game_id':       game['id'],
        'board':         s['board'],
        'goats_placed':  s['goats_placed'],
        'goats_captured': s['goats_captured'],
        'current_turn':  s['current_turn'],
        'phase':         s['phase'],
        'status':        s['status'],
        'tiger_moves':   s['tiger_moves'],
        'goat_moves':    s['goat_moves'],
        'mode':          game['mode'],
        'human_role':    game['human_role'],
        'difficulty':    game['difficulty'],
        'draw_offered':  game['draw_offered'],
        'draw_off_by':   game['draw_off_by'],
        'move_log':      game['move_log'],
        'can_undo':      game['prev_state'] is not None,
        'game_number':   game.get('game_number'),
        'session_id': (
            game.get('session_game_id', '').split('_')[0]
            if game.get('session_game_id') else None
        ),
        'time_limit':     game.get('time_limit'),
        'time_remaining': game.get('time_remaining', game.get('time_limit')),
    }


def _validate_node(value, name: str):
    """Return (int_value, None) or (None, error_response)."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None, (jsonify({'ok': False, 'error': f'{name} must be an integer'}), 400)
    if not (0 <= n < 25):
        return None, (jsonify({'ok': False, 'error': f'{name} out of range (0-24)'}), 400)
    return n, None


def _finalize_game(game: dict, username: str) -> None:
    """Write report, increment counter and persist; call when game just ended."""
    game['end_time'] = time.time()
    report_service.export_game_report(game)
    user_model.increment_games(username)


def _execute_action(game: dict, action: dict) -> dict:
    """
    Apply a human action, run AI follow-up if needed, persist, and return payload.
    The game dict is only mutated after all state transitions succeed.
    """
    s = game['state']
    faction = s['current_turn']
    username = game['username']

    # Snapshot for undo (take before modifying)
    if game['mode'] == 'ai' and faction == game['human_role']:
        game['prev_state'] = copy.deepcopy(s)
    elif game['mode'] == 'hotseat':
        game['prev_state'] = copy.deepcopy(s)

    # Apply human move
    human_ts = time.time()
    human_legal = format_moves_list(GameEngine.get_all_moves(s, faction))
    new_state, captured_node = GameEngine.apply_move(s, action)
    game['state'] = new_state

    # Log human move
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

    if (game['mode'] == 'ai'
            and new_state['status'] == 'active'
            and new_state['current_turn'] != game['human_role']):

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
        _finalize_game(game, username)

    game_store.save_game(game)

    payload = _state_payload(game)
    payload.update({
        'captured_node':  captured_node,
        'ai_action_type': ai_action_type,
        'ai_from':        ai_from,
        'ai_to':          ai_to,
        'ai_captured':    ai_captured,
        'ai_desc':        ai_desc,
    })
    return payload


# ── Routes ────────────────────────────────────────────────────────────────

@game_bp.route('/next', methods=['GET'])
def next_game():
    """Get or create the next game in the session."""
    username = session.get('username')
    if not username:
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401

    sess = session_store.get_session(username)
    if not sess or sess['finished']:
        sess = session_store.new_session(username)

    game_id, num = session_store.get_next_game_id(username)
    if not game_id:
        return jsonify({'ok': False, 'error': 'All games completed'}), 400

    params = Config.SESSION_GAME_PARAMS
    if num not in params:
        return jsonify({'ok': False, 'error': 'Invalid game number'}), 400

    human_role, difficulty = params[num]
    time_limit = Config.TIMED_GAME_LIMIT if num == Config.TIMED_GAME_NUMBER else None

    game_id = game_store.new_game(username, 'ai', human_role, difficulty, session_game_id=f"{sess['session_id']}_{num:03d}")
    game = game_store.get_game(game_id)
    game['game_number'] = num
    game['time_limit'] = time_limit
    game['time_remaining'] = time_limit
    
    # 'tiger' always moves first; if the human was assigned 'goat' for this
    # round, the AI (playing tiger) needs to make its opening move now --
    # otherwise the game sits frozen forever waiting for a "human turn"
    # that never arrives.
    ai_fields = _run_ai_followup(game)
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

    s = game['state']
    turn = s['current_turn']

    if game['mode'] == 'ai' and turn != game['human_role']:
        return jsonify({'ok': False, 'error': 'Not your turn'}), 400

    action_type = data.get('action_type')

    # ── Timeout ──────────────────────────────────────────────────────────
    if action_type == 'timeout':
        # Validate that a time limit actually applies to this game
        if not game.get('time_limit'):
            return jsonify({'ok': False, 'error': 'No time limit for this game'}), 400

        game['state']['status'] = (
            'tiger_win' if game['human_role'] == 'goat' else 'goat_win'
        )
        _finalize_game(game, username)
        game_store.save_game(game)
        return jsonify({'ok': True, **_state_payload(game)})

    # ── Timer enforcement (server-side) ──────────────────────────────────
    if game.get('time_limit') and game.get('start_time'):
        elapsed = time.time() - game['start_time']
        if elapsed >= game['time_limit']:
            game['state']['status'] = (
                'tiger_win' if game['human_role'] == 'goat' else 'goat_win'
            )
            _finalize_game(game, username)
            game_store.save_game(game)
            return jsonify({'ok': True, **_state_payload(game)})

    to_node, err = _validate_node(data.get('to_node'), 'to_node')
    if err:
        return err

    # ── Place ─────────────────────────────────────────────────────────────
    if action_type == 'place':
        if turn != 'goat' or s['phase'] != 1:
            return jsonify({'ok': False, 'error': 'Cannot place now'}), 400
        if s['board'][to_node] is not None:
            return jsonify({'ok': False, 'error': 'Square occupied'}), 400
        action = {'type': 'place', 'to': to_node}

    # ── Move ──────────────────────────────────────────────────────────────
    elif action_type == 'move':
        from_node, err = _validate_node(data.get('from_node'), 'from_node')
        if err:
            return err
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
            'capture': mv['capture'],
        }

    else:
        return jsonify({'ok': False, 'error': 'Unknown action'}), 400

    payload = _execute_action(game, action)

    if game['state']['status'] != 'active':
        sess = session_store.get_session(username)
        payload['next_game_available'] = bool(sess and sess['current_game'] <= 5)

    return jsonify({'ok': True, **payload})


@game_bp.route('/timer', methods=['POST'])
def update_timer():
    """Receive a client-side time_remaining hint (informational only; server enforces on move)."""
    username = session.get('username')
    if not username:
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401

    data = request.get_json() or {}
    game_id = data.get('game_id')
    time_remaining = data.get('time_remaining')

    game = game_store.get_game(game_id)
    if not game or game['username'] != username:
        return jsonify({'ok': False, 'error': 'Game not found'}), 404

    # Store client hint but server enforces based on start_time
    if isinstance(time_remaining, (int, float)) and time_remaining >= 0:
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

    # Remove the logged moves that are being undone
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

    _finalize_game(game, username)
    game_store.save_game(game)

    payload = _state_payload(game)
    sess = session_store.get_session(username)
    payload['next_game_available'] = bool(sess and sess['current_game'] <= 5)
    return jsonify({'ok': True, **payload})


@game_bp.route('/quit_session', methods=['POST'])
def quit_session():
    """
    Quit the current 5-game session. The active game (if any) and every
    round that hadn't been started yet are recorded as forfeited, so the
    session always ends with a complete 5-game record rather than gaps.
    Also used by the client's inactivity timeout and browser-close beacon.
    """
    username = session.get('username')
    if not username:
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    
    data = request.get_json(silent=True) or {}
    game_id = data.get('game_id')
    
    sess = session_store.get_session(username)
    if not sess:
        return jsonify({'ok': True, 'forfeited': []})
    
    forfeited = []
    
    # Forfeit the game currently in progress, if any.
    if game_id:
        game = game_store.get_game(game_id)
        if game and game['username'] == username and game['state']['status'] == 'active':
            _forfeit_game(game)
            forfeited.append(game.get('game_number'))
    
    # Forfeit every round that was never even started.
    if not sess['finished']:
        for num in range(sess['current_game'], 6):
            if num not in SESSION_PARAMS:
                continue
            human_role, difficulty = SESSION_PARAMS[num]
            gid = game_store.new_game(username, 'ai', human_role, difficulty)
            g = game_store.get_game(gid)
            g['game_number'] = num
            g['session_game_id'] = f"{sess['session_id']}_{num:03d}"
            _forfeit_game(g)
            forfeited.append(num)
        sess['current_game'] = 6
    
    session_store.mark_finished(username)
    
    return jsonify({'ok': True, 'forfeited': forfeited})


@game_bp.route('/draw', methods=['POST'])
def draw_offer():
    """Offer, accept, or decline a draw."""
    username = session.get('username')
    if not username:
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401

    data = request.get_json() or {}
    game_id = data.get('game_id')
    action = data.get('action')  # 'offer' | 'accept' | 'decline'

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
            # AI decides immediately (no second human click needed)
            ai_role = 'goat' if game['human_role'] == 'tiger' else 'tiger'
            accepted = ai_service.should_accept_draw(game['state'], ai_role)
            game['draw_offered'] = False
            game['draw_off_by'] = None
            ai_response = 'accepted' if accepted else 'declined'
            if accepted:
                game['state']['status'] = 'draw_agreement'
                _finalize_game(game, username)

        game_store.save_game(game)
        payload = _state_payload(game)
        if ai_response:
            payload['ai_response'] = ai_response
        if game['state']['status'] != 'active':
            sess = session_store.get_session(username)
            payload['next_game_available'] = bool(sess and sess['current_game'] <= 5)
        return jsonify({'ok': True, **payload})

    elif action == 'accept':
        # Only meaningful in hotseat; in AI mode the offer resolves immediately above
        if not game['draw_offered']:
            return jsonify({'ok': False, 'error': 'No draw offer to accept'}), 400

        game['state']['status'] = 'draw_agreement'
        game['draw_offered'] = False
        game['draw_off_by'] = None
        _finalize_game(game, username)
        game_store.save_game(game)

        payload = _state_payload(game)
        sess = session_store.get_session(username)
        payload['next_game_available'] = bool(sess and sess['current_game'] <= 5)
        return jsonify({'ok': True, **payload})

    elif action == 'decline':
        if not game['draw_offered']:
            return jsonify({'ok': False, 'error': 'No draw offer to decline'}), 400

        game['draw_offered'] = False
        game['draw_off_by'] = None
        game_store.save_game(game)
        return jsonify({'ok': True, **_state_payload(game)})

    else:
        return jsonify({'ok': False, 'error': 'Unknown draw action'}), 400
