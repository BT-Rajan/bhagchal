"""
Core Bagh Chal game logic.

Pure functions for board management, move validation, and game state.
No I/O, no Flask dependencies - pure game engine.
"""
import copy
from typing import List, Dict, Any, Optional, Tuple


# Board constants
N = 25  # 5x5 board
CORNERS = [0, 4, 20, 24]

# Position weights for AI evaluation (center control bonus)
CENTER_WEIGHTS = [
    0, 1, 2, 1, 0,
    1, 2, 3, 2, 1,
    2, 3, 4, 3, 2,
    1, 2, 3, 2, 1,
    0, 1, 2, 1, 0,
]


def _build_adjacency() -> List[List[int]]:
    """Build adjacency list for the 5x5 board with orthogonal + diagonal connections."""
    adj = [[] for _ in range(N)]
    
    def idx(r: int, c: int) -> int:
        return r * 5 + c
    
    # Orthogonal connections
    for r in range(5):
        for c in range(5):
            n = idx(r, c)
            if r > 0:
                adj[n].append(idx(r - 1, c))
            if r < 4:
                adj[n].append(idx(r + 1, c))
            if c > 0:
                adj[n].append(idx(r, c - 1))
            if c < 4:
                adj[n].append(idx(r, c + 1))
    
    # Diagonal connections (only where (row+col) % 2 == 0)
    for r in range(4):
        for c in range(5):
            if (r + c) % 2 != 0:
                continue
            if c < 4:
                a, b = idx(r, c), idx(r + 1, c + 1)
                if b not in adj[a]:
                    adj[a].append(b)
                if a not in adj[b]:
                    adj[b].append(a)
            if c > 0:
                a, b = idx(r, c), idx(r + 1, c - 1)
                if b not in adj[a]:
                    adj[a].append(b)
                if a not in adj[b]:
                    adj[b].append(a)
    
    # Remove duplicates while preserving order
    return [list(dict.fromkeys(x)) for x in adj]


# Pre-computed adjacency list
ADJ = _build_adjacency()


class GameEngine:
    """Pure game logic engine for Bagh Chal."""
    
    @staticmethod
    def get_moves_for(state: Dict[str, Any], node: int) -> List[Dict[str, int]]:
        """Get all valid moves for a piece at the given node."""
        piece = state['board'][node]
        if not piece:
            return []
        
        moves = []
        
        if piece == 'tiger':
            for nb in ADJ[node]:
                if state['board'][nb] is None:
                    # Empty adjacent square - can move there
                    moves.append({'to': nb, 'capture': -1})
                elif state['board'][nb] == 'goat':
                    # Check for capture (jump over goat to empty square beyond)
                    dr = (nb // 5) - (node // 5)
                    dc = (nb % 5) - (node % 5)
                    lr = (nb // 5) + dr
                    lc = (nb % 5) + dc
                    
                    if 0 <= lr < 5 and 0 <= lc < 5:
                        dest = lr * 5 + lc
                        if dest in ADJ[nb] and state['board'][dest] is None:
                            moves.append({'to': dest, 'capture': nb})
        
        elif piece == 'goat':
            # Goats can only move in phase 2
            if state['phase'] == 1:
                return []
            for nb in ADJ[node]:
                if state['board'][nb] is None:
                    moves.append({'to': nb, 'capture': -1})
        
        return moves
    
    @staticmethod
    def get_all_moves(state: Dict[str, Any], faction: str) -> List[Dict[str, Any]]:
        """Get all valid moves for a faction."""
        moves = []
        for i in range(N):
            if state['board'][i] == faction:
                for m in GameEngine.get_moves_for(state, i):
                    moves.append({'from': i, **m})
        return moves
    
    @staticmethod
    def check_end(state: Dict[str, Any]) -> str:
        """Check if the game has ended and return the result."""
        # Tiger wins by capturing 5 goats
        if state['goats_captured'] >= 5:
            return 'tiger_win'
        
        # Goat wins by trapping all tigers (no legal tiger moves in phase 2)
        if state['current_turn'] == 'tiger' and len(GameEngine.get_all_moves(state, 'tiger')) == 0:
            return 'goat_win'
        
        # Draw: goat has no legal moves in phase 2 (stalemate)
        if state['phase'] == 2 and state['current_turn'] == 'goat':
            if len(GameEngine.get_all_moves(state, 'goat')) == 0:
                return 'draw_no_moves'
        
        # Draw: same board position repeated 3 times
        if state['phase'] == 2:
            cur_hash = board_hash(state['board'])
            if state['move_history'].get(cur_hash, 0) >= 3:
                return 'draw_repetition'
        
        return 'active'
    
    @staticmethod
    def apply_move(state: Dict[str, Any], action: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """Apply a move/action to the game state. Returns new state and captured node (-1 if none)."""
        ns = copy.deepcopy(state)
        captured_node = -1
        
        if action['type'] == 'place':
            # Place a goat on the board
            ns['board'][action['to']] = 'goat'
            ns['goats_placed'] += 1
            if ns['goats_placed'] == 20:
                ns['phase'] = 2
            ns['goat_moves'] += 1
        
        else:
            # Move a piece
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
        
        # Switch turn
        ns['current_turn'] = 'goat' if ns['current_turn'] == 'tiger' else 'tiger'
        
        # Track board position for repetition detection (phase 2 only)
        if ns['phase'] == 2:
            h = board_hash(ns['board'])
            ns['move_history'][h] = ns['move_history'].get(h, 0) + 1
        
        # Check end conditions
        ns['status'] = GameEngine.check_end(ns)
        
        return ns, captured_node


# ── Helper functions ──────────────────────────────────────────────────────

def init_state() -> Dict[str, Any]:
    """Initialize a fresh game state."""
    board = [None] * N
    for c in CORNERS:
        board[c] = 'tiger'
    
    return {
        'board': board,
        'goats_placed': 0,
        'goats_captured': 0,
        'current_turn': 'tiger',
        'phase': 1,
        'status': 'active',
        'move_history': {},
        'tiger_moves': 0,
        'goat_moves': 0
    }


def board_hash(board: List[Optional[str]]) -> str:
    """Generate a hash string for the board state."""
    return ','.join(x or '' for x in board)


def node_label(n: int) -> str:
    """Convert node index to chess-like notation (A1-E5)."""
    cols = 'ABCDE'
    return f"{cols[n % 5]}{n // 5 + 1}"


def format_move(mv: Dict[str, Any]) -> str:
    """Format a move dict as human-readable string."""
    if mv.get('type') == 'place' or 'from' not in mv:
        return f"place {node_label(mv['to'])}"
    else:
        s = f"{node_label(mv['from'])}→{node_label(mv['to'])}"
        if mv.get('capture', -1) >= 0:
            s += f"✕{node_label(mv['capture'])}"
        return s


def format_moves_list(moves: List[Dict[str, Any]]) -> List[str]:
    """Format a list of moves as strings."""
    return [format_move(m) for m in moves]
