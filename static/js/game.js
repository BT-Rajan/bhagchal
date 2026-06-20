/* game.js — Client-side game controller */
'use strict';

/* ── Tips ── */
const TIPS = [
  {icon:'🐯', text:'<b>Tigers</b> start at the 4 corners. They move one step per turn along any board line.'},
  {icon:'🐐', text:'<b>Goats go first.</b> In Phase 1, place one goat per turn on any empty intersection.'},
  {icon:'⚔️', text:'<b>Tiger captures:</b> jump over an adjacent goat to an empty square along a valid line.'},
  {icon:'🚫', text:'<b>Goats cannot jump</b> and cannot capture. Their weapon is position.'},
  {icon:'🎯', text:'<b>Tigers win</b> by capturing 5 goats. Always look for capture threats before moving.'},
  {icon:'🔒', text:'<b>Goats win</b> by surrounding all 4 tigers so none can move. Restrict mobility.'},
  {icon:'🌀', text:'<b>Phase 2</b> begins when all 20 goats are placed. Goats can now move one step per turn.'},
  {icon:'🤝', text:'<b>Draw rules:</b> goat stalemate in Phase 2, or threefold repetition, is a draw.'},
  {icon:'📍', text:'<b>Goat strategy:</b> place early goats near the centre. Central goats cut off tiger diagonals.'},
  {icon:'🏹', text:'<b>Tiger strategy:</b> keep two tigers with open lines to threaten captures together.'},
];
let _tipIdx = 0;
function showTip(idx) {
  _tipIdx = ((idx % TIPS.length) + TIPS.length) % TIPS.length;
  const t = TIPS[_tipIdx];
  const el = $id('tip-text');
  if (el) el.innerHTML = `${t.icon} &nbsp;${t.text}`;
  const num = $id('tip-num');
  if (num) num.textContent = `${_tipIdx+1}/${TIPS.length}`;
}
window.tipNext = () => showTip(_tipIdx + 1);
window.tipPrev = () => showTip(_tipIdx - 1);

/* ── Result display data ── */
const RESULTS = {
  tiger_win:       { icon:'🐯', title:'Tigers Win!',       sub:'5 goats captured.' },
  goat_win:        { icon:'🐐', title:'Goats Win!',        sub:'All tigers are trapped.' },
  draw_agreement:  { icon:'🤝', title:'Draw Agreed',       sub:'Both players agreed to a draw.' },
  draw_no_moves:   { icon:'⚖️', title:'Draw',              sub:'Goats have no legal moves.' },
  draw_repetition: { icon:'🔄', title:'Draw',              sub:'Threefold repetition.' },
  tiger_resigned:  { icon:'🏳️', title:'Tigers Resigned',   sub:'Goats win by forfeit.' },
  goat_resigned:   { icon:'🏳️', title:'Goats Resigned',    sub:'Tigers win by forfeit.' },
};

/* ── State ── */
let _gameId        = null;
let _state         = null;   // always the LATEST server state (post-human, post-AI)
let _selected      = -1;
let _validMoves    = [];
let _locked        = false;  // blocks all board interaction
let _handoverShown = false;

/* Timer */
let _timerInterval = null;
let _timeRemaining = 0;
let _isTimedGame   = false;

/* ── DOM helpers ── */
function $id(id) { return document.getElementById(id); }
function $cls(id, op, ...args) { const el=$id(id); if(el) el.classList[op](...args); }

function setStatus(msg, cls='') {
  const el = $id('status-bar');
  if (!el) return;
  el.textContent = msg;
  el.className = 'status-bar' + (cls ? ' '+cls : '');
}

/* ── Server helpers ── */
async function post(url, body={}) {
  const r = await fetch(url, {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify(body)
  });
  if (!r.ok) {
    let msg;
    try { msg = (await r.json()).error || `HTTP ${r.status}`; }
    catch(e) { msg = `HTTP ${r.status}`; }
    throw new Error(msg);
  }
  return r.json();
}
async function get(url) {
  const r = await fetch(url);
  if (!r.ok) {
    let msg;
    try { msg = (await r.json()).error || `HTTP ${r.status}`; }
    catch(e) { msg = `HTTP ${r.status}`; }
    throw new Error(msg);
  }
  return r.json();
}

/* ── Node label ── */
function nodeLabel(n) { return 'ABCDE'[n%5] + (Math.floor(n/5)+1); }

/* ── Client-side move generator (for highlight only — server authoritative) ── */
function getClientMoves(state, node) {
  const board = state.board;
  const piece = board[node];
  if (!piece) return [];
  const moves = [];
  if (piece === 'tiger') {
    for (const nb of Board.ADJ[node]) {
      if (board[nb] === null) {
        moves.push({to: nb, capture: -1});
      } else if (board[nb] === 'goat') {
        const dr = Math.floor(nb/5) - Math.floor(node/5);
        const dc = (nb%5) - (node%5);
        const lr = Math.floor(nb/5) + dr;
        const lc = (nb%5) + dc;
        if (lr>=0 && lr<5 && lc>=0 && lc<5) {
          const dest = lr*5 + lc;
          if (Board.ADJ[nb].includes(dest) && board[dest] === null)
            moves.push({to: dest, capture: nb});
        }
      }
    }
  } else if (piece === 'goat' && state.phase === 2) {
    for (const nb of Board.ADJ[node]) {
      if (board[nb] === null) moves.push({to: nb, capture: -1});
    }
  }
  return moves;
}

/* ── Timer ── */
function startTimer(limit) {
  _timeRemaining = limit;
  _renderTimer();
  const td = $id('timer-display');
  if (td) td.style.display = 'block';
  if (_timerInterval) clearInterval(_timerInterval);
  _timerInterval = setInterval(() => {
    _timeRemaining--;
    _renderTimer();
    if (_timeRemaining % 5 === 0) {
      post('/api/game/timer', {game_id:_gameId, time_remaining:_timeRemaining})
        .catch(()=>{});
    }
    if (_timeRemaining <= 0) {
      clearInterval(_timerInterval);
      setStatus('⏰ Time is up!', 'err');
      doAction('timeout', {});
    }
  }, 1000);
}
function _renderTimer() {
  const el = $id('timer-display');
  if (!el) return;
  const m = Math.floor(_timeRemaining/60);
  const s = _timeRemaining % 60;
  el.textContent = `${m}:${s.toString().padStart(2,'0')}`;
  el.classList.toggle('urgent', _timeRemaining < 60);
}
function stopTimer() {
  if (_timerInterval) { clearInterval(_timerInterval); _timerInterval = null; }
}

/* ── Start next game ── */
async function startNextGame() {
  _locked = false;
  _handoverShown = false;
  _selected = -1;
  _validMoves = [];
  stopTimer();
  const modal = $id('win-modal');
  if (modal) { const b=modal.querySelector('.next-game-modal-btn'); if(b) b.remove(); }
  $cls('win-modal',       'remove','show');
  $cls('phase-overlay',   'remove','show');
  $cls('handover-overlay','remove','show');
  $cls('draw-banner',     'remove','show');
  const drawBtn = $id('draw-btn');
  if (drawBtn) { drawBtn.disabled=false; drawBtn.textContent='Offer Draw'; }
  const ngBtn = $id('next-game-btn');
  if (ngBtn) { ngBtn.style.display='none'; ngBtn.disabled=true; }

  try {
    const d = await get('/api/game/next');
    if (!d.ok || d.error) {
      setStatus(d.error || 'Session complete!', 'ok');
      return;
    }
    _gameId = d.game_id;
    _state  = d;
    showGameScreen();
    _resetInactivityTimer();

    // Render the initial board (before any AI animation)
    // Use the board BEFORE the AI opening move, i.e. fresh init board
    // The server sends the board AFTER the AI opening move in d.board.
    // We need to reconstruct the pre-AI-move board for the initial render,
    // then animate the AI's opening move.
    // Strategy: always show d.board immediately if no AI opening move is pending,
    // otherwise show a clean init board then animate.
    if (d.ai_action_type && d.ai_to != null && d.ai_to >= 0) {
      // Build and show the pre-AI board (initial board with tigers at corners only)
      const preBoard = _buildPreAIBoard(d);
      Board.setBoard(preBoard);
      Board.setSelected(-1);
      Board.setValidMoves([]);
      Board.draw();
      updateUI(d);
      rebuildLog([]);  // no human moves logged yet

      // Show AI "thinking" delay then animate
      _locked = true;
      setStatus('Engine is processing…', 'info');
      const delayMs = _aiDelay();
      setTimeout(() => {
        const from = d.ai_from >= 0 ? d.ai_from : d.ai_to;
        const piece = d.ai_action_type === 'place' ? 'goat'
                    : (d.human_role === 'tiger' ? 'goat' : 'tiger');
        Board.animateMove(from, d.ai_to, piece, d.ai_captured ?? -1, () => {
          // Now the animation is done — update board to final state
          Board.setBoard(d.board);
          Board.draw();
          updateUI(d);
          rebuildLog(d.move_log || []);
          _locked = false;
          postMoveStatus();
        });
      }, delayMs);
    } else {
      // Human moves first — just show the board
      Board.setBoard(d.board);
      Board.setSelected(-1);
      Board.setValidMoves([]);
      Board.draw();
      updateUI(d);
      rebuildLog(d.move_log || []);
      postMoveStatus();
    }

    if (d.time_limit) {
      _isTimedGame = true;
      startTimer(d.time_limit);
    } else {
      _isTimedGame = false;
      const td = $id('timer-display');
      if (td) td.style.display = 'none';
    }
  } catch(e) {
    setStatus('Error: '+e.message, 'err');
  }
}

/* Build the board state BEFORE the AI's opening move by reversing it.
   For tiger opening move: put tiger back at ai_from, clear ai_to. */
function _buildPreAIBoard(d) {
  const pre = Array.from(d.board);  // copy final board
  if (d.ai_action_type === 'move' && d.ai_from >= 0) {
    pre[d.ai_from] = pre[d.ai_to];  // put piece back
    pre[d.ai_to]   = null;
    if (d.ai_captured >= 0) pre[d.ai_captured] = 'goat';  // restore captured goat
  } else if (d.ai_action_type === 'place') {
    pre[d.ai_to] = null;  // remove placed goat
  }
  return pre;
}

/* Non-uniform random delay 1500ms–5200ms */
function _aiDelay() {
  return Math.round(1500 + Math.pow(Math.random(), 0.6) * 3700);
}

/* ── UI updates ── */
function updateUI(d) {
  if (!d) return;
  const gameNumEl = $id('game-number');
  if (gameNumEl) gameNumEl.textContent = `${d.game_number||'?'} / 5`;
  const sidEl = $id('session-id');
  if (sidEl) sidEl.textContent = `SID ${d.session_id||'—'}`;

  $id('captured-count').textContent = d.goats_captured;
  $id('placed-count').textContent   = `${d.goats_placed} / 20`;
  $id('reserve-count').textContent  = `${20 - d.goats_placed}`;
  $id('phase-label').textContent    = d.phase===1 ? 'Phase I — Placement' : 'Phase II — Movement';
  $id('tiger-moves').textContent    = d.tiger_moves;
  $id('goat-moves').textContent     = d.goat_moves;
  document.querySelectorAll('.cap-pip').forEach((p,i) => p.classList.toggle('filled', i < d.goats_captured));

  // Goat reserve pips
  const res = $id('goat-reserve');
  if (res) {
    res.innerHTML = '';
    for (let i=0; i<20; i++) {
      const pip = document.createElement('div');
      pip.className = 'goat-pip' +
        (i < d.goats_captured ? ' captured' : i < d.goats_placed ? ' used' : '');
      res.appendChild(pip);
    }
  }

  // Turn indicators
  const isGoat = d.current_turn === 'goat';
  const ti = $id('tiger-turn-ind'), gi = $id('goat-turn-ind');
  if (ti) { ti.className='turn-ind'+(isGoat?' inactive':' active');       ti.textContent=isGoat?'Standby':'▶ Active'; }
  if (gi) { gi.className='turn-ind'+(isGoat?' active goat-t':' inactive'); gi.textContent=isGoat?'▶ Active':'Standby'; }

  const undoBtn = $id('undo-btn');
  if (undoBtn) undoBtn.disabled = !d.can_undo;

  // Draw banner (hotseat only)
  if (d.draw_offered && d.mode==='hotseat') {
    $cls('draw-banner','add','show');
    const msg = $id('draw-banner-msg');
    if (msg) msg.textContent = `${d.draw_off_by==='tiger'?'Tigers':'Goats'} offer a draw. Accept?`;
  } else {
    $cls('draw-banner','remove','show');
  }
}

/* ── Status line ── */
function postMoveStatus() {
  if (!_state) return;
  const d = _state;
  if (d.status !== 'active') { showResult(d.status); return; }

  if (d.mode === 'hotseat') {
    const who = d.current_turn==='tiger' ? '🐯 Tiger' : '🐐 Goat';
    setStatus(`${who}'s turn — ${d.phase===1 && d.current_turn==='goat' ? 'place a goat' : 'select a piece to move'}.`);
    showHandover(d.current_turn, d.phase);
    return;
  }
  // vs AI
  if (d.current_turn !== d.human_role) {
    setStatus('Engine is processing…', 'info');
    return;
  }
  if (d.phase === 1) {
    setStatus(d.current_turn==='goat'
      ? '🐐 Your turn — click any empty intersection to place a goat.'
      : '🐯 Your turn — select a tiger to move or capture.', 'd.current_turn==="goat"?'ok':'');
  } else {
    setStatus(`${d.current_turn==='goat'?'🐐':'🐯'} Your turn — select a piece and move it.`);
  }
  showTip(Math.floor(Math.random()*TIPS.length));
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
    const n = document.createElement('span'); n.className='move-num'; n.textContent=`${e.num}.`;
    const ic = document.createElement('span'); ic.className='move-icon'; ic.textContent=e.faction==='tiger'?'🐯':'🐐';
    const ds = document.createElement('span'); ds.className='move-desc'; ds.textContent=e.desc;
    row.append(n,ic,ds);
    if (e.is_capture) {
      const b = document.createElement('span'); b.className='move-badge cap'; b.textContent='✕';
      row.appendChild(b);
    }
    scroll.appendChild(row);
  }
  scroll.scrollTop = scroll.scrollHeight;
  const dot = $id('save-dot');
  if (dot) { dot.classList.add('flash'); setTimeout(()=>dot.classList.remove('flash'),800); }
}

/* ── Canvas interaction ── */
function onCanvasClick(e) {
  if (!_state || _state.status!=='active' || _locked) return;
  if (_state.draw_offered) return;
  if (_state.mode==='ai' && _state.current_turn!==_state.human_role) {
    setStatus('Engine is processing — please wait…', 'info');
    return;
  }

  const canvas = $id('board');
  const rect = canvas.getBoundingClientRect();
  const x = (e.clientX - rect.left) * (canvas.width / rect.width);
  const y = (e.clientY - rect.top)  * (canvas.height / rect.height);
  const node = Board.nearest(x, y);
  if (node < 0) return;

  const turn  = _state.current_turn;
  const board = _state.board;

  // Phase 1 goat placement
  if (turn==='goat' && _state.phase===1) {
    if (board[node] !== null) { setStatus('That spot is occupied.','err'); return; }
    doAction('place', {to_node: node});
    return;
  }

  // Select or move
  if (_selected < 0) {
    if (board[node] === turn) {
      _selected = node;
      _validMoves = getClientMoves(_state, node);
      Board.setSelected(node);
      Board.setValidMoves(_validMoves);
      if (!_validMoves.length) {
        setStatus('No valid moves from this piece.','warn');
        _selected=-1; Board.setSelected(-1); Board.setValidMoves([]);
      } else {
        const caps = _validMoves.filter(m=>m.capture>=0).length;
        setStatus(`${turn==='tiger'?'Tiger':'Goat'} at ${nodeLabel(node)} selected${caps?' — '+caps+' capture'+(caps>1?'s':''):''}. Choose destination.`);
      }
      Board.draw();
    } else if (board[node] !== null) {
      setStatus(`It's the ${turn}'s turn.`, 'err');
    }
    return;
  }

  if (_selected === node) {
    _selected=-1; _validMoves=[];
    Board.setSelected(-1); Board.setValidMoves([]);
    setStatus('Selection cleared.'); Board.draw();
    return;
  }

  const mv = _validMoves.find(m=>m.to===node);
  if (mv) {
    doAction('move', {from_node: _selected, to_node: mv.to});
  } else if (board[node]===turn) {
    _selected = node;
    _validMoves = getClientMoves(_state, node);
    Board.setSelected(node); Board.setValidMoves(_validMoves);
    if (!_validMoves.length) { setStatus('No valid moves.','warn'); _selected=-1; Board.setSelected(-1); }
    else setStatus(`Reselected ${nodeLabel(node)}.`);
    Board.draw();
  } else {
    setStatus('Invalid destination.','err');
  }
}

function onCanvasHover(e) {
  if (_locked || !_state) return;
  const canvas = $id('board');
  const rect = canvas.getBoundingClientRect();
  const x = (e.clientX-rect.left)*(canvas.width/rect.width);
  const y = (e.clientY-rect.top)*(canvas.height/rect.height);
  Board.setHover(Board.nearest(x,y));
  Board.draw();
}

/* ── Send action ── */
async function doAction(actionType, extra={}) {
  _locked = true;
  _selected = -1; _validMoves = [];
  Board.setSelected(-1); Board.setValidMoves([]);
  $cls('board','add','blocked');
  setStatus('Transmitting…','info');

  const body = {game_id:_gameId, action_type:actionType, ...extra};
  let d;
  try {
    d = await post('/api/game/move', body);
  } catch(e) {
    _locked = false;
    $cls('board','remove','blocked');
    setStatus('Error: '+e.message,'err');
    Board.draw();
    return;
  }
  $cls('board','remove','blocked');

  const wasPhase1 = _state && _state.phase===1;

  // ── Step 1: animate the HUMAN move on the PRE-move board ──────────────
  // _state still holds the pre-move board at this point.
  // We animate the human piece moving, then handle the AI in the callback.
  const humanFrom    = extra.from_node != null ? extra.from_node : extra.to_node;
  const humanTo      = extra.to_node;
  const humanPiece   = _state ? _state.current_turn : 'goat';
  const humanCapture = (d.captured_node >= 0) ? d.captured_node : -1;

  const afterHumanAnim = () => {
    // Board now visually matches d.board (the post-human, pre-AI board)
    // For placement, d.board already has the placed goat — show it.
    // Update state to post-human board (before AI move)
    const justEnteredPhase2 = wasPhase1 && d.phase===2 && d.status==='active';

    if (d.ai_action_type && d.ai_to >= 0 && d.status==='active') {
      // ── Step 2: show post-human board, then animate AI ──────────────
      // Build intermediate board: d.board IS the final board (after both moves).
      // We need the board AFTER human, BEFORE AI, to show correctly before animating AI.
      const midBoard = _buildPreAIBoard(d);
      Board.setBoard(midBoard);
      Board.draw();
      updateUI_partial(d);  // update stats but keep turn indicators in "AI thinking" state

      setStatus('Engine is processing…','info');
      setTimeout(() => {
        const aiFrom  = d.ai_from >= 0 ? d.ai_from : d.ai_to;
        const aiPiece = d.human_role==='tiger' ? 'goat' : 'tiger';
        Board.animateMove(aiFrom, d.ai_to, aiPiece, d.ai_captured ?? -1, () => {
          // ── Step 3: apply final state ────────────────────────────────
          _state = d;
          Board.setBoard(d.board);
          Board.draw();
          updateUI(d);
          rebuildLog(d.move_log || []);
          _locked = false;
          if (d.status !== 'active') { showResult(d.status); }
          else if (justEnteredPhase2) { showPhaseOverlay(); }
          else { postMoveStatus(); }
          _showNextGameBtn(d);
        });
      }, _aiDelay());

    } else {
      // ── No AI move (game over, or hotseat) ──────────────────────────
      _state = d;
      Board.setBoard(d.board);
      Board.draw();
      updateUI(d);
      rebuildLog(d.move_log || []);
      _locked = false;
      if (d.status !== 'active') { showResult(d.status); }
      else if (justEnteredPhase2) { showPhaseOverlay(); }
      else { postMoveStatus(); }
      _showNextGameBtn(d);
    }
  };

  // Animate human move; for placement (phase 1) skip animation — just update board
  if (actionType === 'move') {
    // Animate move on current (pre-move) board
    Board.animateMove(humanFrom, humanTo, humanPiece, humanCapture, afterHumanAnim);
  } else if (actionType === 'place') {
    // Placement: add the goat to the current board visually, then proceed
    // Build intermediate board with placed goat
    const midBoard = Array.from(_state.board);
    midBoard[humanTo] = 'goat';
    Board.setBoard(midBoard);
    Board.draw();
    afterHumanAnim();
  } else {
    // timeout or other special action
    afterHumanAnim();
  }
}

/* Update stats/pips without changing turn indicators (used mid-sequence) */
function updateUI_partial(d) {
  $id('captured-count').textContent = d.goats_captured;
  $id('placed-count').textContent   = `${d.goats_placed} / 20`;
  $id('reserve-count').textContent  = `${20 - d.goats_placed}`;
  $id('tiger-moves').textContent    = d.tiger_moves;
  $id('goat-moves').textContent     = d.goat_moves;
  document.querySelectorAll('.cap-pip').forEach((p,i)=>p.classList.toggle('filled', i < d.goats_captured));
  const res = $id('goat-reserve');
  if (res) {
    res.innerHTML='';
    for (let i=0;i<20;i++){
      const pip=document.createElement('div');
      pip.className='goat-pip'+(i<d.goats_captured?' captured':i<d.goats_placed?' used':'');
      res.appendChild(pip);
    }
  }
}

/* Build board state BEFORE the AI's move from the final board */
function _buildPreAIBoard(d) {
  const pre = Array.from(d.board);
  if (d.ai_action_type==='move' && d.ai_from >= 0) {
    pre[d.ai_from] = pre[d.ai_to];
    pre[d.ai_to]   = null;
    if ((d.ai_captured ?? -1) >= 0) pre[d.ai_captured] = 'goat';
  } else if (d.ai_action_type==='place' && d.ai_to >= 0) {
    pre[d.ai_to] = null;
  }
  return pre;
}

function _aiDelay() {
  return Math.round(1500 + Math.pow(Math.random(), 0.6) * 3700);
}

function _showNextGameBtn(d) {
  if (d.next_game_available) {
    const btn = $id('next-game-btn');
    if (btn) { btn.style.display='inline-block'; btn.disabled=false; }
  }
}

/* ── Apply server state (undo / resign / draw) ── */
function applyServerState(d) {
  _state = d;
  _selected=-1; _validMoves=[];
  Board.setBoard(d.board);
  Board.setSelected(-1); Board.setValidMoves([]);
  updateUI(d);
  rebuildLog(d.move_log || []);
  Board.draw();
  if (d.status !== 'active') { stopTimer(); showResult(d.status); }
  else { postMoveStatus(); }
  const drawBtn = $id('draw-btn');
  if (drawBtn && !d.draw_offered) { drawBtn.disabled=false; drawBtn.textContent='Offer Draw'; }
  _showNextGameBtn(d);
  _locked = false;
}

/* ── Game actions ── */
window.doUndo = async function() {
  if (!_gameId || _locked) return;
  _locked = true;
  try {
    const d = await post('/api/game/undo', {game_id:_gameId});
    applyServerState(d);
  } catch(e) {
    setStatus('Error: '+e.message,'err');
    _locked = false;
  }
};

window.doResign = async function() {
  if (!_gameId || _locked) return;
  if (!confirm('Resign? The opponent wins.')) return;
  stopTimer(); _locked=true;
  try {
    const d = await post('/api/game/resign', {game_id:_gameId});
    applyServerState(d);
  } catch(e) {
    setStatus('Error: '+e.message,'err');
    _locked=false;
  }
};

window.doOfferDraw = async function() {
  if (!_gameId || _locked) return;
  _locked=true;
  const btn=$id('draw-btn');
  if (btn) { btn.disabled=true; btn.textContent='Awaiting…'; }
  try {
    const d = await post('/api/game/draw', {game_id:_gameId, action:'offer'});
    applyServerState(d);
    if (d.ai_response==='accepted') {
      setStatus('Computer accepted the draw.','ok');
      if (d.status!=='active') showResult(d.status);
    } else if (d.ai_response==='declined') {
      setStatus('Computer declined the draw offer.','warn');
      if (btn) { btn.disabled=false; btn.textContent='Offer Draw'; }
    }
  } catch(e) {
    setStatus('Error: '+e.message,'err');
    if (btn) { btn.disabled=false; btn.textContent='Offer Draw'; }
  } finally { _locked=false; }
};

window.doAcceptDraw = async function() {
  if (!_gameId) return;
  try { applyServerState(await post('/api/game/draw',{game_id:_gameId,action:'accept'})); }
  catch(e) { setStatus('Error: '+e.message,'err'); }
};

window.doDeclineDraw = async function() {
  if (!_gameId) return;
  try { applyServerState(await post('/api/game/draw',{game_id:_gameId,action:'decline'})); }
  catch(e) { setStatus('Error: '+e.message,'err'); }
};

/* ── Hotseat handover ── */
function showHandover(turn, phase) {
  if (_handoverShown) return;
  _handoverShown=true; _locked=true;
  const icon=$id('handover-icon'), title=$id('handover-title'), sub=$id('handover-sub');
  if (icon) icon.textContent = turn==='tiger'?'🐯':'🐐';
  if (title) { title.textContent=turn==='tiger'?"Tiger's Turn":"Goat's Turn"; title.className='handover-faction '+turn; }
  if (sub) sub.textContent = phase===1?'Pass the device.':'Pass the device.';
  $cls('handover-overlay','add','show');
}
window.dismissHandover = function() {
  $cls('handover-overlay','remove','show');
  _handoverShown=false; _locked=false; Board.draw();
};

/* ── Phase overlay ── */
function showPhaseOverlay() { _locked=true; $cls('phase-overlay','add','show'); }
window.dismissPhaseOverlay = function() { $cls('phase-overlay','remove','show'); _locked=false; Board.draw(); };

/* ── Next game ── */
window.goToNextGame = function() {
  const btn=$id('next-game-btn');
  if (btn) { btn.style.display='none'; btn.disabled=true; }
  stopTimer(); startNextGame();
};

/* ── Result modal ── */
function showResult(status) {
  const r = RESULTS[status] || {icon:'🎮',title:'Game Over',sub:''};
  $id('modal-icon').textContent  = r.icon;
  $id('modal-title').textContent = r.title;
  $id('modal-sub').textContent   = r.sub;
  if (_state) {
    $id('modal-stats').innerHTML = `
      <div class="modal-stat"><div class="n" style="color:var(--tiger)">${_state.tiger_moves}</div><div class="l">Tiger moves</div></div>
      <div class="modal-stat"><div class="n">${(_state.move_log||[]).length}</div><div class="l">Total moves</div></div>
      <div class="modal-stat"><div class="n" style="color:var(--capture)">${_state.goats_captured}</div><div class="l">Captured</div></div>`;
  }
  $cls('win-modal','add','show');
  if (_state && _state.next_game_available) {
    const modal = $id('win-modal');
    if (!modal.querySelector('.next-game-modal-btn')) {
      const btn = document.createElement('button');
      btn.className='btn btn-primary next-game-modal-btn';
      btn.textContent='▶ Next Assessment';
      btn.onclick=()=>{ $cls('win-modal','remove','show'); window.goToNextGame(); };
      modal.querySelector('.overlay-card').appendChild(btn);
    }
  }
}

/* ── Screen routing ── */
function showGameScreen() {
  $id('role-screen').style.display='none';
  $id('game-screen').style.display='block';
  const res=$id('goat-reserve');
  if (res) {
    res.innerHTML='';
    for (let i=0;i<20;i++){
      const d=document.createElement('div'); d.className='goat-pip'; res.appendChild(d);
    }
  }
}

window.goToLobby = async function() {
  Board.cancelAnim(); stopTimer(); _clearInactivityTimer();
  $cls('win-modal','remove','show'); $cls('phase-overlay','remove','show');
  $cls('handover-overlay','remove','show'); $cls('draw-banner','remove','show');
  try { await post('/api/game/quit_session',{game_id:_gameId}); } catch(e){}
  _gameId=null; _state=null; _selected=-1; _validMoves=[]; _locked=false; _handoverShown=false;
  const btn=$id('draw-btn'); if(btn){btn.disabled=false;btn.textContent='Offer Draw';}
  const ng=$id('next-game-btn'); if(ng){ng.style.display='none';ng.disabled=true;}
  window.location.replace('/?t='+Date.now());
};

/* ── Inactivity ── */
const INACTIVITY_MS = 10*60*1000;
let _inactivityTimer = null;
function _resetInactivityTimer() {
  if (_inactivityTimer) clearTimeout(_inactivityTimer);
  if (!_gameId || !_state || _state.status!=='active') return;
  _inactivityTimer = setTimeout(()=>{ alert('Inactive for 10 minutes. Session ending.'); goToLobby(); }, INACTIVITY_MS);
}
function _clearInactivityTimer() { if(_inactivityTimer){clearTimeout(_inactivityTimer);_inactivityTimer=null;} }

window.addEventListener('beforeunload', ()=>{
  if (_gameId) navigator.sendBeacon('/api/game/quit_session',
    new Blob([JSON.stringify({game_id:_gameId})],{type:'application/json'}));
});

/* ── Init ── */
window.startNextGame = startNextGame;

window.addEventListener('DOMContentLoaded', () => {
  Board.init('board');
  const canvas = $id('board');
  if (canvas) {
    canvas.addEventListener('click', e=>{ _resetInactivityTimer(); onCanvasClick(e); });
    canvas.addEventListener('mousemove', onCanvasHover);
    canvas.addEventListener('mouseleave', ()=>{ Board.setHover(-1); Board.draw(); });
  }
  ['click','keydown','touchstart'].forEach(evt=>
    document.addEventListener(evt, _resetInactivityTimer, {passive:true}));
  // Do NOT auto-start — user must click "Begin Assessment"
  showTip(0);
});
