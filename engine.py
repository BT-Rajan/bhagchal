"""
engine.py — Pure Baghchal game logic (no I/O, no Flask, no state).
Ported 1-to-1 from the JS Engine module. All functions are pure.
"""

N = 25
CORNERS = [0, 4, 20, 24]

CENTER_WEIGHTS = [
    0, 1, 2, 1, 0,
    1, 2, 3, 2, 1,
    2, 3, 4, 3, 2,
    1, 2, 3, 2, 1,
    0, 1, 2, 1, 0,
]

def _build_adj():
    adj = [[] for _ in range(N)]
    def idx(r, c): return r * 5 + c
    for r in range(5):
        for c in range(5):
            n = idx(r, c)
            if r > 0: adj[n].append(idx(r-1, c))
            if r < 4: adj[n].append(idx(r+1, c))
            if c > 0: adj[n].append(idx(r, c-1))
            if c < 4: adj[n].append(idx(r, c+1))
    for r in range(4):
        for c in range(5):
            if (r + c) % 2 != 0:
                continue
            if c < 4:
                a, b = idx(r, c), idx(r+1, c+1)
                if b not in adj[a]: adj[a].append(b)
                if a not in adj[b]: adj[b].append(a)
            if c > 0:
                a, b = idx(r, c), idx(r+1, c-1)
                if b not in adj[a]: adj[a].append(b)
                if a not in adj[b]: adj[b].append(a)
    return [list(dict.fromkeys(x)) for x in adj]

ADJ = _build_adj()

def board_hash(board):
    return ','.join(x or '' for x in board)

def get_moves_for(state, node):
    piece = state['board'][node]
    if not piece:
        return []
    moves = []
    if piece == 'tiger':
        for nb in ADJ[node]:
            if state['board'][nb] is None:
                moves.append({'to': nb, 'capture': -1})
            elif state['board'][nb] == 'goat':
                dr = (nb // 5) - (node // 5)
                dc = (nb % 5)  - (node % 5)
                lr = (nb // 5) + dr
                lc = (nb % 5)  + dc
                if 0 <= lr < 5 and 0 <= lc < 5:
                    dest = lr * 5 + lc
                    if dest in ADJ[nb] and state['board'][dest] is None:
                        moves.append({'to': dest, 'capture': nb})
    elif piece == 'goat':
        if state['phase'] == 1:
            return []
        for nb in ADJ[node]:
            if state['board'][nb] is None:
                moves.append({'to': nb, 'capture': -1})
    return moves

def get_all_moves(state, faction):
    moves = []
    for i in range(N):
        if state['board'][i] == faction:
            for m in get_moves_for(state, i):
                moves.append({'from': i, **m})
    return moves

def check_end(state):
    if state['goats_captured'] >= 5:
        return 'tiger_win'
    if (state['phase'] == 2
            and state['current_turn'] == 'goat'
            and len(get_all_moves(state, 'goat')) == 0):
        return 'draw_no_moves'
    if (state['current_turn'] == 'tiger'
            and len(get_all_moves(state, 'tiger')) == 0):
        return 'goat_win'
    if state['phase'] == 2:
        cur = board_hash(state['board'])
        if state['move_history'].get(cur, 0) >= 3:
            return 'draw_repetition'
    return 'active'

def apply_move(state, action):
    import copy
    ns = copy.deepcopy(state)
    captured_node = -1

    if action['type'] == 'place':
        ns['board'][action['to']] = 'goat'
        ns['goats_placed'] += 1
        if ns['goats_placed'] == 20:
            ns['phase'] = 2
        ns['goat_moves'] += 1
    else:
        ns['board'][action['to']] = ns['board'][action['from']]
        ns['board'][action['from']] = None
        captured_node = action.get('capture', -1)
        if captured_node >= 0:
            ns['board'][captured_node] = None
            ns['goats_captured'] += 1
        if ns['board'][action['to']] == 'tiger':
            ns['tiger_moves'] += 1
        else:
            ns['goat_moves'] += 1

    ns['current_turn'] = 'goat' if ns['current_turn'] == 'tiger' else 'tiger'

    if ns['phase'] == 2:
        h = board_hash(ns['board'])
        ns['move_history'][h] = ns['move_history'].get(h, 0) + 1

    ns['status'] = check_end(ns)
    return ns, captured_node

def init_state():
    board = [None] * N
    for c in CORNERS:
        board[c] = 'tiger'
    return {
        'board':         board,
        'goats_placed':  0,
        'goats_captured':0,
        'current_turn':  'tiger',
        'phase':         1,
        'status':        'active',
        'move_history':  [],
        'tiger_moves':   0,
        'goat_moves':    0,
    }

def node_label(n):
    cols = 'ABCDE'
    return f"{cols[n % 5]}{n // 5 + 1}"

# ---- New formatting helpers for logging ----

def format_move(mv):
    """Return a human-readable string for a move dict (from get_all_moves)."""
    if mv.get('type') == 'place' or 'from' not in mv:
        # placement
        return f"place {node_label(mv['to'])}"
    else:
        s = f"{node_label(mv['from'])}→{node_label(mv['to'])}"
        if mv.get('capture', -1) >= 0:
            s += f"✕{node_label(mv['capture'])}"
        return s

def format_moves_list(moves):
    """Return list of string representations of moves."""
    return [format_move(m) for m in moves]