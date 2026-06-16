"""
ai.py — Minimax AI with Alpha-Beta Pruning.
Ported from JS AI module. Two heuristics: Tiger and Goat.
"""
import random
from engine import (
    N, ADJ, CENTER_WEIGHTS, get_moves_for, get_all_moves,
    check_end, board_hash, apply_move
)

DEPTH_MAP = {'easy': 1, 'medium': 3, 'hard': 4}


# ── Heuristic evaluation ──────────────────────────────────────────────────────

def evaluate(state):
    end = check_end(state)
    if end == 'tiger_win':       return  100_000
    if end == 'goat_win':        return -100_000
    if end in ('draw_no_moves', 'draw_repetition'): return 0

    score = 0

    # Tiger: captures, mobility, capture threats
    score += state['goats_captured'] * 1000
    tiger_moves = get_all_moves(state, 'tiger')
    score += len(tiger_moves) * 10
    cap_threats = [m for m in tiger_moves if m['capture'] >= 0]
    score += len(cap_threats) * 80

    # Per-tiger trap penalty (once per tiger, not per edge)
    for t in range(N):
        if state['board'][t] != 'tiger':
            continue
        local = len(get_moves_for(state, t))
        if local == 0:
            score -= 300
        elif local <= 2:
            score -= 50

    # Goat wall score (deduplicated goat-goat adjacent pairs)
    seen = set()
    for g in range(N):
        if state['board'][g] != 'goat':
            continue
        for nb in ADJ[g]:
            if state['board'][nb] != 'goat':
                continue
            key = (min(g, nb), max(g, nb))
            if key not in seen:
                seen.add(key)
                score -= 20

    # Threatened goats (deduplicated by capture node)
    threatened = {m['capture'] for m in cap_threats}
    score -= len(threatened) * 100

    # Phase 1: penalise goats away from centre
    if state['phase'] == 1:
        for i in range(N):
            if state['board'][i] == 'goat':
                score -= CENTER_WEIGHTS[i] * 5

    return score


# ── Fast apply for Minimax (no deepcopy overhead) ────────────────────────────

def _fast_apply(state, action):
    """Lightweight state copy for minimax — skips move counters."""
    board = list(state['board'])
    goats_placed   = state['goats_placed']
    goats_captured = state['goats_captured']
    phase          = state['phase']
    move_history   = state['move_history']   # shared ref until we push

    if action['type'] == 'place':
        board[action['to']] = 'goat'
        goats_placed += 1
        if goats_placed == 20:
            phase = 2
    else:
        board[action['to']] = board[action['from']]
        board[action['from']] = None
        cap = action.get('capture', -1)
        if cap >= 0:
            board[cap] = None
            goats_captured += 1

    current_turn = 'goat' if state['current_turn'] == 'tiger' else 'tiger'

    if phase == 2:
        h = board_hash(board)
        move_history = dict(move_history)
        move_history[h] = move_history.get(h, 0) + 1
    else:
        move_history = move_history  # same ref is fine (Phase 1 never tracks)

    return {
        'board':          board,
        'goats_placed':   goats_placed,
        'goats_captured': goats_captured,
        'current_turn':   current_turn,
        'phase':          phase,
        'status':         'active',
        'move_history':   move_history,
        'tiger_moves':    0,
        'goat_moves':     0,
    }


# ── Minimax ───────────────────────────────────────────────────────────────────

def minimax(state, depth, alpha, beta, maximizing):
    end = check_end(state)
    if end != 'active':
        return evaluate(state)
    if depth == 0:
        return evaluate(state)

    faction = 'tiger' if maximizing else 'goat'

    if faction == 'goat' and state['phase'] == 1:
        # Placement candidates (centre-first, pruned at high depth)
        candidates = [6,7,8,11,12,13,16,17,18,0,2,4,10,14,20,22,24,1,3,5,9,15,19,21,23]
        limit = 12 if depth >= 3 else N
        moves_iter = []
        for to in candidates:
            if state['board'][to] is None:
                moves_iter.append({'type': 'place', 'to': to, 'from': -1, 'capture': -1})
                if len(moves_iter) >= limit:
                    break
    else:
        raw = get_all_moves(state, faction)
        # Move ordering: captures first (improves alpha-beta cutoffs)
        raw.sort(key=lambda m: 0 if m['capture'] >= 0 else 1)
        moves_iter = [{'type': 'move', **m} for m in raw]

    if not moves_iter:
        return evaluate(state)

    if maximizing:
        best = -float('inf')
        for mv in moves_iter:
            ns = _fast_apply(state, mv)
            val = minimax(ns, depth - 1, alpha, beta, False)
            if val > best:
                best = val
            if val > alpha:
                alpha = val
            if beta <= alpha:
                break
        return best
    else:
        best = float('inf')
        for mv in moves_iter:
            ns = _fast_apply(state, mv)
            val = minimax(ns, depth - 1, alpha, beta, True)
            if val < best:
                best = val
            if val < beta:
                beta = val
            if beta <= alpha:
                break
        return best


# ── Best move selector ────────────────────────────────────────────────────────

def find_best_move(state, ai_role, difficulty='medium'):
    depth = DEPTH_MAP.get(difficulty, 3)

    # Easy: pure random
    if difficulty == 'easy':
        if ai_role == 'goat' and state['phase'] == 1:
            empty = [i for i in range(N) if state['board'][i] is None]
            if not empty:
                return None
            return {'type': 'place', 'to': random.choice(empty), 'from': -1, 'capture': -1}
        all_moves = get_all_moves(state, ai_role)
        if not all_moves:
            return None
        mv = random.choice(all_moves)
        return {'type': 'move', **mv}

    maximizing = (ai_role == 'tiger')

    # Goat placement (Phase 1)
    if ai_role == 'goat' and state['phase'] == 1:
        candidates = [12,6,8,16,18,7,11,13,17,2,10,14,22,0,4,20,24,1,3,5,9,15,19,21,23]
        best_score = float('inf')
        best_to    = -1
        for to in candidates:
            if state['board'][to] is not None:
                continue
            ns = _fast_apply(state, {'type': 'place', 'to': to, 'from': -1, 'capture': -1})
            score = minimax(ns, depth - 1, -float('inf'), float('inf'), True)
            score += random.uniform(-5, 5)   # tie-breaking jitter for variety
            if score < best_score:
                best_score = score
                best_to    = to
        return {'type': 'place', 'to': best_to, 'from': -1, 'capture': -1} if best_to >= 0 else None

    # Movement
    raw = get_all_moves(state, ai_role)
    if not raw:
        return None
    raw.sort(key=lambda m: 0 if m['capture'] >= 0 else 1)  # captures first

    best_score = -float('inf') if maximizing else float('inf')
    best_moves = [raw[0]]

    for mv in raw:
        ns = _fast_apply(state, {'type': 'move', **mv})
        score = minimax(ns, depth - 1, -float('inf'), float('inf'), not maximizing)
        if maximizing:
            if score > best_score:
                best_score = score
                best_moves = [mv]
            elif score == best_score:
                best_moves.append(mv)
        else:
            if score < best_score:
                best_score = score
                best_moves = [mv]
            elif score == best_score:
                best_moves.append(mv)

    chosen = random.choice(best_moves)
    return {'type': 'move', **chosen}


def evaluate_for_draw(state, ai_role):
    """Returns True if AI is losing enough to accept a draw."""
    score = evaluate(state)
    return score > 2000 if ai_role == 'goat' else score < -2000
