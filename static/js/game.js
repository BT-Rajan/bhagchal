/* game.js — Client-side game controller with 5-game session support */
'use strict';

/* ── Tips ── */
const TIPS = [
  {icon:'🐯', text:'<b>Tigers</b> start at the 4 corners. They move one step per turn along any board line.'},
  {icon:'🐐', text:'<b>Goats go first.</b> In Phase 1, place one goat per turn on any empty intersection.'},
  {icon:'⚔️', text:'<b>Tiger captures:</b> jump over an adjacent goat to an empty square along a valid line. One jump per turn.'},
  {icon:'🚫', text:'<b>Goats cannot jump</b> and cannot capture. Their weapon is position.'},
  {icon:'🎯', text:'<b>Tigers win</b> by capturing 5 goats. Always look for capture threats before moving.'},
  {icon:'🔒', text:'<b>Goats win</b> by surrounding all 4 tigers so none can move. Restrict mobility.'},
  {icon:'🌀', text:'<b>Phase 2</b> begins when all 20 goats are placed. Goats can now move one step per turn.'},
  {icon:'🤝', text:'<b>Draw rules:</b> goat stalemate in Phase 2 is a draw. Threefold repetition is also a draw.'},
  {icon:'📍', text:'<b>Goat strategy:</b> place early goats near the centre (C3). Central goats cut off tiger diagonals.'},
  {icon:'🏹', text:'<b>Tiger strategy:</b> never isolate all four tigers. Keep two with open lines to threaten captures together.'},
];
let _tipIdx = 0;
function showTip(idx) {
  _tipIdx = ((idx % TIPS.length) + TIPS.length) % TIPS.length;
  const t = TIPS[_tipIdx];
  const el = document.getElementById('tip-text');
  if (el) el.innerHTML = `${t.icon} &nbsp;${t.text}`;
  const num = document.getElementById('tip-num');
  if (num) num.textContent = `${_tipIdx+1}/${TIPS.length}`;
}
window.tipNext = () => showTip(_tipIdx + 1);
window.tipPrev = () => showTip(_tipIdx - 1);

/* ── Game-over result display data ── */
const RESULTS = {
  tiger_win:       { icon: '🐯', title: 'Tigers Win!',  sub: '5 goats captured. The hunt is over.' },
  goat_win:        { icon: '🐐', title: 'Goats Win!',   sub: 'All tigers are trapped. The herd prevails.' },
  draw_agreement:  { icon: '🤝', title: 'Draw Agreed',  sub: 'Both players agreed to a draw.' },
  draw_no_moves:   { icon: '⚖️', title: 'Draw',         sub: 'Goats have no legal moves. Draw.' },
  draw_repetition: { icon: '🔄', title: 'Draw',         sub: 'Threefold repetition. Draw.' },
  tiger_resigned:  { icon: '🏳️', title: 'Tigers Resigned', sub: 'Goats win by forfeit.' },
  goat_resigned:   { icon: '🏳️', title: 'Goats Resigned',  sub: 'Tigers win by forfeit.' },
};

/* ── State ── */
let _gameId     = null;
let _state      = null;
let _selected   = -1;
let _validMoves = [];
let _locked     = false;
let _handoverShown = false;

// Timer state
let _timerInterval = null;
let _timeRemaining = 0;
let _isTimedGame = false;

/* ── DOM helpers ── */
function $id(id) { return document.getElementById(id); }
function $cls(id, op, ...args) {
  const el = $id(id);
  if (el) el.classList[op](...args);
}
function setStatus(msg, cls = '') {
  const el = $id('status-bar');
  if (!el) return;
  el.textContent = msg;
  el.className = 'status-bar' + (cls ? ' ' + cls : '');
}

/* ── Server communication ── */
async function post(url, body = {}) {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!r.ok) {
    const errText = await r.text();
    let errMsg;
    try {
      const j = JSON.parse(errText);
      errMsg = j.error || j.message || `HTTP ${r.status}`;
    } catch (e) {
      errMsg = `HTTP ${r.status} - ${errText}`;
    }
    throw new Error(errMsg);
  }
  return r.json();
}
async function get(url) {
  const r = await fetch(url);
  if (!r.ok) {
    const errText = await r.text();
    let errMsg;
    try {
      const j = JSON.parse(errText);
      errMsg = j.error || j.message || `HTTP ${r.status}`;
    } catch (e) {
      errMsg = `HTTP ${r.status} - ${errText}`;
    }
    throw new Error(errMsg);
  }
  return r.json();
}

/* ── Session: start next game ── */
async function startNextGame() {
  console.log('Fetching next game...');
  // Reset all per-round state so nothing bleeds from the previous round.
  _locked = false;
  _handoverShown = false;
  _selected = -1;
  _validMoves = [];
  stopTimer();
  // Remove any "Next Game" button cloned into the modal by showResult().
  const modal = $id('win-modal');
  if (modal) {
    const cloned = modal.querySelector('.next-game-modal-btn');
    if (cloned) cloned.remove();
  }
  $cls('win-modal',      'remove', 'show');
  $cls('phase-overlay',  'remove', 'show');
  $cls('handover-overlay','remove','show');
  $cls('draw-banner',    'remove', 'show');
  const drawBtn = $id('draw-btn');
  if (drawBtn) { drawBtn.disabled = false; drawBtn.textContent = 'Offer Draw'; }
  const ngBtn = $id('next-game-btn');
  if (ngBtn) { ngBtn.style.display = 'none'; ngBtn.disabled = true; }

  try {
    const d = await get('/api/game/next');
    if (!d.ok || d.error) {
      setStatus(d.error || 'Session complete!', 'ok');
      const btn = $id('next-game-btn');
      if (btn) { btn.disabled = true; btn.textContent = 'Session Complete'; }
      return;
    }
    applyState(d);
    showGameScreen();
    _resetInactivityTimer();
    if (d.time_limit) {
      _isTimedGame = true;
      startTimer(d.time_limit);
    } else {
      _isTimedGame = false;
      const td = $id('timer-display');
      if (td) td.style.display = 'none';
    }
  } catch (e) {
    console.error('startNextGame error:', e);
    setStatus('Error: ' + e.message, 'err');
    alert('Error: ' + e.message);
  }
}

/* ── Timer ── */
function startTimer(limit) {
  _timeRemaining = limit;
  updateTimerDisplay();
  const timerEl = $id('timer-display');
  if (timerEl) timerEl.style.display = 'block';
  if (_timerInterval) clearInterval(_timerInterval);
  _timerInterval = setInterval(() => {
    _timeRemaining--;
    updateTimerDisplay();
    // Send remaining time to server every 5 seconds
    if (_timeRemaining % 5 === 0) {
      post('/api/game/timer', { game_id: _gameId, time_remaining: _timeRemaining })
        .catch(e => console.warn('Timer update failed:', e));
    }
    if (_timeRemaining <= 0) {
      clearInterval(_timerInterval);
      setStatus('⏰ Time is up! You lose.', 'err');
      // Force a game over by sending an empty action; server will detect timeout.
      doAction('timeout', {});
    }
  }, 1000);
}

function updateTimerDisplay() {
  const el = $id('timer-display');
  if (!el) return;
  const mins = Math.floor(_timeRemaining / 60);
  const secs = _timeRemaining % 60;
  el.textContent = `${mins}:${secs.toString().padStart(2, '0')}`;
  if (_timeRemaining < 60) el.style.color = '#e85050';
  else el.style.color = 'var(--gold)';
}

function stopTimer() {
  if (_timerInterval) {
    clearInterval(_timerInterval);
    _timerInterval = null;
  }
}

/* ── Apply server state ── */
function applyState(d) {
  _gameId = d.game_id;
  _state = d;
  _selected = -1;
  _validMoves = [];
  Board.setBoard(d.board);
  Board.setSelected(-1);
  Board.setValidMoves([]);
  updateUI(d);
  Board.draw();

  if (d.ai_action_type && d.ai_to != null && d.ai_to >= 0) {
    _locked = true;
    setStatus('Engine is processing…', 'info');
    const u = Math.random();
    const delayMs = Math.round(1500 + (Math.pow(u, 0.6) * 3700));
    setTimeout(() => {
      const from = d.ai_from >= 0 ? d.ai_from : d.ai_to;
      const piece = d.ai_action_type === 'place' ? 'goat' :
        (d.human_role === 'tiger' ? 'goat' : 'tiger');
      Board.animateMove(from, d.ai_to, piece, d.ai_captured, () => {
        _locked = false;
        postMoveStatus();
      });
    }, delayMs);
  } else {
    postMoveStatus();
  }
  rebuildLog(d.move_log || []);
}

/* ── UI updates ── */
function updateUI(d) {
  if (!d) return;
  // Game number / session info
  const gameNumEl = $id('game-number');
  if (gameNumEl) gameNumEl.textContent = `Game ${d.game_number || '?'} / 5`;
  const sessionIdEl = $id('session-id');
  if (sessionIdEl) sessionIdEl.textContent = `Session: ${d.session_id || ''}`;

  $id('captured-count').textContent = d.goats_captured;
  $id('placed-count').textContent = `${d.goats_placed} / 20`;
  $id('reserve-count').textContent = `${20 - d.goats_placed}`;
  $id('phase-label').textContent = d.phase === 1 ? 'Phase I — Placement' : 'Phase II — Movement';
  $id('tiger-moves').textContent = d.tiger_moves;
  $id('goat-moves').textContent = d.goat_moves;
  document.querySelectorAll('.cap-pip').forEach((p, i) => p.classList.toggle('filled', i < d.goats_captured));

  const res = $id('goat-reserve');
  if (res) {
    res.innerHTML = '';
    for (let i = 0; i < 20; i++) {
      const pip = document.createElement('div');
      pip.className = 'goat-pip' + (i < d.goats_captured ? ' captured' : i < d.goats_placed ? ' used' : '');
      res.appendChild(pip);
    }
  }

  const isGoat = (d.current_turn === 'goat');
  const ti = $id('tiger-turn-ind'), gi = $id('goat-turn-ind');
  if (ti) { ti.className = 'turn-ind' + (!isGoat ? ' active' : ' inactive'); ti.textContent = !isGoat ? '▶ Active' : 'Standby'; }
  if (gi) { gi.className = 'turn-ind' + (isGoat ? ' active goat-t' : ' inactive'); gi.textContent = isGoat ? '▶ Active' : 'Standby'; }

  const undoBtn = $id('undo-btn');
  if (undoBtn) undoBtn.disabled = !d.can_undo;

  if (d.draw_offered && d.mode === 'hotseat') {
    $cls('draw-banner', 'add', 'show');
    const msg = $id('draw-banner-msg');
    if (msg) msg.textContent = `${d.draw_off_by === 'tiger' ? 'Tigers' : 'Goats'} offer a draw. Accept?`;
  } else {
    $cls('draw-banner', 'remove', 'show');
  }
}

function postMoveStatus() {
  if (!_state) return;
  const d = _state;
  if (d.status !== 'active') { showResult(d.status); return; }
  const t = d.current_turn;
  if (d.mode === 'ai' && t !== d.human_role) {
    setStatus('Engine is processing…', 'info');
    return;
  }
  if (d.mode === 'hotseat') {
    const who = t === 'tiger' ? '🐯 Tiger' : '🐐 Goat';
    if (d.phase === 1) {
      setStatus(`${who}'s turn — ` + (t === 'goat' ? 'place a goat on any empty intersection' : 'select a tiger to move or capture'), t === 'goat' ? 'ok' : '');
    } else {
      setStatus(`${who}'s turn — select and move a piece.`, '');
    }
    showHandover(t, d.phase);
    return;
  }
  // vs AI — human's turn
  if (d.phase === 1) {
    setStatus(t === 'goat' ? '🐐 Your turn — place a goat on any empty intersection.' : '🐯 Your turn — select a tiger to move or capture.', t === 'goat' ? 'ok' : '');
  } else {
    setStatus(`${t === 'goat' ? '🐐' : '🐯'} Your turn — select and move a piece.`, '');
  }
  showTip(Math.floor(Math.random() * TIPS.length));
}

/* ── Move log ── */
function rebuildLog(log) {
  const scroll = $id('history-scroll');
  if (!scroll) return;
  scroll.innerHTML = '';
  if (!log.length) {
    scroll.innerHTML = '<div style="font-size:11px;color:var(--text-dim);text-align:center;padding:8px 0">No moves yet.</div>';
    return;
  }
  for (const e of log) {
    const row = document.createElement('div');
    row.className = 'move-entry';
    const n = document.createElement('span');
    n.className = 'move-num';
    n.textContent = `${e.num}.`;
    const ic = document.createElement('span');
    ic.className = 'move-icon';
    ic.textContent = e.faction === 'tiger' ? '🐯' : '🐐';
    const ds = document.createElement('span');
    ds.className = 'move-desc';
    ds.textContent = e.desc;
    row.appendChild(n);
    row.appendChild(ic);
    row.appendChild(ds);
    if (e.is_capture) {
      const b = document.createElement('span');
      b.className = 'move-badge cap';
      b.textContent = '×1';
      row.appendChild(b);
    }
    scroll.appendChild(row);
  }
  scroll.scrollTop = scroll.scrollHeight;
  const dot = $id('save-dot');
  if (dot) { dot.classList.add('flash'); setTimeout(() => dot.classList.remove('flash'), 800); }
}

/* ── Board interaction ── */
function onCanvasClick(e) {
  if (!_state || _state.status !== 'active' || _locked) return;
  if (_state.draw_offered) return;
  if (_state.mode === 'ai' && _state.current_turn !== _state.human_role) {
    setStatus('Engine is processing — please wait…', 'info');
    return;
  }

  const canvas = $id('board');
  const rect = canvas.getBoundingClientRect();
  const x = (e.clientX - rect.left) * (canvas.width / rect.width);
  const y = (e.clientY - rect.top) * (canvas.height / rect.height);
  const node = Board.nearest(x, y);
  if (node < 0) return;

  const turn = _state.current_turn;
  const board = _state.board;

  if (turn === 'goat' && _state.phase === 1) {
    if (board[node] !== null) { setStatus('That spot is occupied.', 'err'); return; }
    doAction('place', { to_node: node });
    return;
  }

  if (_selected < 0) {
    if (board[node] === turn) {
      _selected = node;
      _validMoves = getClientMoves(_state, node);
      Board.setSelected(node);
      Board.setValidMoves(_validMoves);
      if (!_validMoves.length) {
        setStatus('No valid moves from this piece.', 'warn');
        _selected = -1;
        Board.setSelected(-1);
        Board.setValidMoves([]);
      } else {
        const caps = _validMoves.filter(m => m.capture >= 0).length;
        setStatus(turn === 'tiger' ?
          `Tiger at ${nodeLabel(node)} selected${caps ? ' — ' + caps + ' capture' + (caps > 1 ? 's' : '') : ''}. Choose destination.` :
          `Goat at ${nodeLabel(node)} selected. Choose destination.`);
      }
      Board.draw();
    } else if (board[node] !== null) {
      setStatus(`It's the ${turn}'s turn.`, 'err');
    }
    return;
  }

  if (_selected === node) {
    _selected = -1;
    _validMoves = [];
    Board.setSelected(-1);
    Board.setValidMoves([]);
    setStatus('Selection cleared.');
    Board.draw();
    return;
  }

  const mv = _validMoves.find(m => m.to === node);
  if (mv) {
    doAction('move', { from_node: _selected, to_node: mv.to });
  } else if (board[node] === turn) {
    _selected = node;
    _validMoves = getClientMoves(_state, node);
    Board.setSelected(node);
    Board.setValidMoves(_validMoves);
    if (!_validMoves.length) { setStatus('No valid moves.', 'warn'); _selected = -1; Board.setSelected(-1); }
    else setStatus(`Reselected ${nodeLabel(node)}.`);
    Board.draw();
  } else {
    setStatus('Invalid destination.', 'err');
  }
}

function onCanvasHover(e) {
  if (_locked || !_state) return;
  const canvas = $id('board');
  const rect = canvas.getBoundingClientRect();
  const x = (e.clientX - rect.left) * (canvas.width / rect.width);
  const y = (e.clientY - rect.top) * (canvas.height / rect.height);
  Board.setHover(Board.nearest(x, y));
  Board.draw();
}

/* ── Client-side move calculation ── */
function getClientMoves(state, node) {
  const board = state.board;
  const piece = board[node];
  if (!piece) return [];
  const moves = [];
  if (piece === 'tiger') {
    for (const nb of Board.ADJ[node]) {
      if (board[nb] === null) { moves.push({ to: nb, capture: -1 }); }
      else if (board[nb] === 'goat') {
        const dr = Math.floor(nb / 5) - Math.floor(node / 5);
        const dc = (nb % 5) - (node % 5);
        const lr = Math.floor(nb / 5) + dr;
        const lc = (nb % 5) + dc;
        if (lr >= 0 && lr < 5 && lc >= 0 && lc < 5) {
          const dest = lr * 5 + lc;
          if (Board.ADJ[nb].includes(dest) && board[dest] === null) {
            moves.push({ to: dest, capture: nb });
          }
        }
      }
    }
  }
  if (piece === 'goat') {
    if (state.phase === 1) return [];
    for (const nb of Board.ADJ[node]) {
      if (board[nb] === null) moves.push({ to: nb, capture: -1 });
    }
  }
  return moves;
}

function nodeLabel(n) {
  return 'ABCDE'[n % 5] + (Math.floor(n / 5) + 1);
}

/* ── Send action to server ── */
async function doAction(actionType, extra = {}) {
  _locked = true;
  _selected = -1;
  _validMoves = [];
  Board.setSelected(-1);
  Board.setValidMoves([]);
  $cls('board', 'add', 'blocked');
  setStatus('Transmitting…', 'info');

  const body = { game_id: _gameId, action_type: actionType, ...extra };
  let d;
  try {
    d = await post('/api/game/move', body);
  } catch (e) {
    _locked = false;
    $cls('board', 'remove', 'blocked');
    setStatus('Error: ' + e.message, 'err');
    alert('Action error: ' + e.message);
    Board.draw();
    return;
  }
  $cls('board', 'remove', 'blocked');

  // If this action ended the game, check if next game is available
  if (d.next_game_available) {
    // Show a "Next Game" button
    const btn = $id('next-game-btn');
    if (btn) {
      btn.style.display = 'inline-block';
      btn.disabled = false;
      btn.textContent = '▶ Next Assessment';
    }
    // Stop timer if any
    stopTimer();
    _locked = true; // prevent board interactions until next game
    // The afterHuman flow will handle UI update
  }

  const fromNode = extra.from_node != null ? extra.from_node : (extra.to_node);
  const toNode = extra.to_node;
  const piece = _state ? _state.current_turn : 'goat';
  const capturedNode = d.captured_node >= 0 ? d.captured_node : -1;
  const wasPhase1 = _state && _state.phase === 1;

  const afterHuman = () => {
    _state = d;
    Board.setBoard(d.board);
    const justEnteredPhase2 = wasPhase1 && d.phase === 2 && d.status === 'active';

    if (d.ai_action_type && d.ai_to >= 0) {
      // Non-uniform delay: skewed toward 2-3s, occasionally slow (up to 5.2s)
      const u = Math.random();
      const delayMs = Math.round(1500 + (Math.pow(u, 0.6) * 3700));
      setStatus('Engine is processing…', 'info');
      setTimeout(() => {
        setStatus('Engine responded.', 'info');
        const aiFrom = d.ai_from >= 0 ? d.ai_from : d.ai_to;
        const aiPiece = d.human_role === 'tiger' ? 'goat' : 'tiger';
        Board.animateMove(aiFrom, d.ai_to, aiPiece, d.ai_captured, () => {
          updateUI(d);
          rebuildLog(d.move_log || []);
          _locked = false;
          Board.setBoard(d.board);
          Board.draw();
          postMoveStatus();
          if (d.status !== 'active') showResult(d.status);
          else if (justEnteredPhase2) showPhaseOverlay();
          if (d.next_game_available) {
            const btn = $id('next-game-btn');
            if (btn) { btn.style.display = 'inline-block'; btn.disabled = false; }
          }
        });
      }, delayMs);
    } else {
      updateUI(d);
      rebuildLog(d.move_log || []);
      _locked = false;
      Board.draw();
      postMoveStatus();
      if (d.status !== 'active') showResult(d.status);
      else if (justEnteredPhase2) showPhaseOverlay();
      if (d.next_game_available) {
        const btn = $id('next-game-btn');
        if (btn) { btn.style.display = 'inline-block'; btn.disabled = false; }
      }
    }
  };

  if (actionType === 'move' || (actionType === 'place' && !wasPhase1)) {
    Board.animateMove(fromNode, toNode, piece, capturedNode, afterHuman);
  } else {
    Board.setBoard(d.board);
    Board.draw();
    afterHuman();
  }
}

/* ── Apply a fresh server state (used by undo/resign/draw responses) ── */
function applyServerState(d) {
  _state = d;
  _selected = -1;
  _validMoves = [];
  _locked = false;   // always unlock — resign/draw ends the game visually via modal, not _locked
  Board.setBoard(d.board);
  Board.setSelected(-1);
  Board.setValidMoves([]);
  updateUI(d);
  rebuildLog(d.move_log || []);
  Board.draw();
  if (d.status !== 'active') {
    stopTimer();
    showResult(d.status);
  } else {
    postMoveStatus();
  }
  const drawBtn = $id('draw-btn');
  if (drawBtn && !d.draw_offered) {
    drawBtn.disabled = false;
    drawBtn.textContent = 'Offer Draw';
  }
  if (d.next_game_available) {
    const btn = $id('next-game-btn');
    if (btn) { btn.style.display = 'inline-block'; btn.disabled = false; }
  }
}

/* ── Game actions ── */
window.doUndo = async function() {
  if (!_gameId || _locked) return;
  _locked = true;
  try {
    const d = await post('/api/game/undo', { game_id: _gameId });
    applyServerState(d);
  } catch (e) {
    setStatus('Error: ' + e.message, 'err');
    alert('Undo error: ' + e.message);
  } finally {
    _locked = false;
  }
};

window.doResign = async function() {
  if (!_gameId || _locked) return;
  if (!confirm('Are you sure you want to resign? The opponent will be declared the winner.')) return;
  stopTimer();
  _locked = true;
  try {
    const d = await post('/api/game/resign', { game_id: _gameId });
    applyServerState(d);
    // applyServerState calls postMoveStatus which calls showResult for non-active.
    // _locked is reset by applyServerState; showResult freezes the board visually
    // via the modal, not via _locked, so the modal buttons stay clickable.
  } catch (e) {
    setStatus('Error: ' + e.message, 'err');
    alert('Resign error: ' + e.message);
    _locked = false;
  }
};

window.doOfferDraw = async function() {
  if (!_gameId || _locked) return;
  _locked = true;
  const btn = $id('draw-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Awaiting…'; }
  try {
    const d = await post('/api/game/draw', { game_id: _gameId, action: 'offer' });
    if (!d.ok) { setStatus(d.error || 'Draw offer failed.', 'err'); return; }
    applyServerState(d);
    if (d.ai_response === 'accepted') {
      setStatus('Computer accepted the draw.', 'ok');
      if (d.status !== 'active') showResult(d.status);
    } else if (d.ai_response === 'declined') {
      setStatus('Computer declined the draw offer.', 'warn');
      if (btn) { btn.disabled = false; btn.textContent = 'Offer Draw'; }
    }
  } catch (e) {
    setStatus('Error: ' + e.message, 'err');
    if (btn) { btn.disabled = false; btn.textContent = 'Offer Draw'; }
  } finally {
    _locked = false;
  }
};

window.doAcceptDraw = async function() {
  if (!_gameId) return;
  try {
    const d = await post('/api/game/draw', { game_id: _gameId, action: 'accept' });
    applyServerState(d);
  } catch (e) {
    setStatus('Error: ' + e.message, 'err');
    alert('Draw error: ' + e.message);
  }
};

window.doDeclineDraw = async function() {
  if (!_gameId) return;
  try {
    const d = await post('/api/game/draw', { game_id: _gameId, action: 'decline' });
    applyServerState(d);
  } catch (e) {
    setStatus('Error: ' + e.message, 'err');
    alert('Draw error: ' + e.message);
  }
};

/* ── Hotseat "pass the device" handover overlay ── */
function showHandover(turn, phase) {
  if (_handoverShown) return;
  _handoverShown = true;
  _locked = true;
  const icon = $id('handover-icon');
  const title = $id('handover-title');
  const sub = $id('handover-sub');
  if (icon) icon.textContent = turn === 'tiger' ? '🐯' : '🐐';
  if (title) {
    title.textContent = turn === 'tiger' ? "Tiger's Turn" : "Goat's Turn";
    title.className = 'handover-title ' + turn;
  }
  if (sub) sub.textContent = phase === 1 ? 'Pass the device — place a goat or move a tiger.' : 'Pass the device.';
  $cls('handover-overlay', 'add', 'show');
}

window.dismissHandover = function() {
  $cls('handover-overlay', 'remove', 'show');
  _handoverShown = false;
  _locked = false;
  Board.draw();
};

/* ── Phase 1 -> Phase 2 transition overlay ── */
function showPhaseOverlay() {
  _locked = true;
  $cls('phase-overlay', 'add', 'show');
}

window.dismissPhaseOverlay = function() {
  $cls('phase-overlay', 'remove', 'show');
  _locked = false;
  Board.draw();
};

/* ── Next Game button handler ── */
window.goToNextGame = function() {
  const btn = $id('next-game-btn');
  if (btn) { btn.style.display = 'none'; btn.disabled = true; }
  stopTimer();
  startNextGame();
};

/* ── Result modal with next game option ── */
function showResult(status) {
  const r = RESULTS[status] || { icon: '🎮', title: 'Game Over', sub: '' };
  $id('modal-icon').textContent = r.icon;
  $id('modal-title').textContent = r.title;
  $id('modal-sub').textContent = r.sub;
  if (_state) {
    $id('modal-stats').innerHTML = `
      <div class="modal-stat"><div class="n" style="color:var(--tiger)">${_state.tiger_moves}</div><div class="l">Tiger moves</div></div>
      <div class="modal-stat"><div class="n">${(_state.move_log || []).length}</div><div class="l">Total moves</div></div>
      <div class="modal-stat"><div class="n" style="color:var(--capture)">${_state.goats_captured}</div><div class="l">Captured</div></div>`;
  }
  $cls('win-modal', 'add', 'show');
  // Add "Next Game" button in modal if available
  if (_state && _state.next_game_available) {
    const modal = $id('win-modal');
    const existing = modal.querySelector('.next-game-modal-btn');
    if (!existing) {
      const btn = document.createElement('button');
      btn.className = 'btn primary next-game-modal-btn';
      btn.textContent = '▶ Next Assessment';
      btn.onclick = () => {
        $cls('win-modal', 'remove', 'show');
        window.goToNextGame();
      };
      modal.querySelector('.overlay-card').appendChild(btn);
    }
  }
}

/* ── Screen routing ── */
function showGameScreen() {
  $id('role-screen').style.display = 'none';
  $id('game-screen').style.display = 'block';
  const res = $id('goat-reserve');
  if (res) {
    res.innerHTML = '';
    for (let i = 0; i < 20; i++) {
      const d = document.createElement('div');
      d.className = 'goat-pip';
      res.appendChild(d);
    }
  }
}

window.goToLobby = async function() {
  Board.cancelAnim();
  stopTimer();
  _clearInactivityTimer();
  $cls('win-modal',       'remove', 'show');
  $cls('phase-overlay',   'remove', 'show');
  $cls('handover-overlay','remove', 'show');
  $cls('draw-banner',     'remove', 'show');

  // Forfeit current game + any unplayed rounds in this session.
  try {
    await post('/api/game/quit_session', { game_id: _gameId });
  } catch (e) {
    console.warn('quit_session failed:', e.message);
  }

  _gameId = null;
  _state  = null;
  _selected = -1;
  _validMoves = [];
  _locked = false;
  _handoverShown = false;
  const btn = $id('draw-btn');
  if (btn) { btn.disabled = false; btn.textContent = 'Offer Draw'; }
  const ng = $id('next-game-btn');
  if (ng) { ng.style.display = 'none'; ng.disabled = true; }
  window.location.replace('/?t=' + Date.now());
};

/* ── Inactivity timeout (10 minutes) ── */
const INACTIVITY_MS = 10 * 60 * 1000;
let _inactivityTimer = null;

function _resetInactivityTimer() {
  if (_inactivityTimer) clearTimeout(_inactivityTimer);
  if (!_gameId || !_state || _state.status !== 'active') return;
  _inactivityTimer = setTimeout(() => {
    alert('You have been inactive for 10 minutes. The session will be ended.');
    goToLobby();
  }, INACTIVITY_MS);
}

function _clearInactivityTimer() {
  if (_inactivityTimer) { clearTimeout(_inactivityTimer); _inactivityTimer = null; }
}

/* ── Browser/tab close: fire-and-forget beacon to quit the session ── */
window.addEventListener('beforeunload', () => {
  if (_gameId) {
    const body = JSON.stringify({ game_id: _gameId });
    // sendBeacon is the only API guaranteed to complete during unload.
    navigator.sendBeacon('/api/game/quit_session', new Blob([body], { type: 'application/json' }));
  }
});

/* ── Init ── */
window.addEventListener('DOMContentLoaded', () => {
  Board.init('board');
  const canvas = $id('board');
  if (canvas) {
    canvas.addEventListener('click', e => { _resetInactivityTimer(); onCanvasClick(e); });
    canvas.addEventListener('mousemove', onCanvasHover);
    canvas.addEventListener('mouseleave', () => { Board.setHover(-1); Board.draw(); });
  }
  // Reset inactivity timer on any user interaction anywhere on the page.
  ['click', 'keydown', 'touchstart'].forEach(evt =>
    document.addEventListener(evt, _resetInactivityTimer, { passive: true })
  );
  // Auto-start the first game.
  startNextGame();
});