/* board.js — Canvas renderer. Pure drawing, no game logic. */
'use strict';

const N = 25;
const ADJ = buildADJ();

function buildADJ() {
  const adj = Array.from({ length: N }, () => []);
  const idx = (r, c) => r * 5 + c;
  for (let r = 0; r < 5; r++) {
    for (let c = 0; c < 5; c++) {
      const n = idx(r, c);
      if (r > 0) adj[n].push(idx(r - 1, c));
      if (r < 4) adj[n].push(idx(r + 1, c));
      if (c > 0) adj[n].push(idx(r, c - 1));
      if (c < 4) adj[n].push(idx(r, c + 1));
    }
  }
  for (let r = 0; r < 4; r++) {
    for (let c = 0; c < 5; c++) {
      if ((r + c) % 2 !== 0) continue;
      if (c < 4) {
        const a = idx(r, c),
          b = idx(r + 1, c + 1);
        if (!adj[a].includes(b)) adj[a].push(b);
        if (!adj[b].includes(a)) adj[b].push(a);
      }
      if (c > 0) {
        const a = idx(r, c),
          b = idx(r + 1, c - 1);
        if (!adj[a].includes(b)) adj[a].push(b);
        if (!adj[b].includes(a)) adj[b].push(a);
      }
    }
  }
  return adj.map(arr => [...new Set(arr)]);
}

if (!CanvasRenderingContext2D.prototype.roundRect) {
  CanvasRenderingContext2D.prototype.roundRect = function(x, y, w, h, r) {
    const R = Math.min(r, w / 2, h / 2);
    this.beginPath();
    this.moveTo(x + R, y);
    this.arcTo(x + w, y, x + w, y + h, R);
    this.arcTo(x + w, y + h, x, y + h, R);
    this.arcTo(x, y + h, x, y, R);
    this.arcTo(x, y, x + w, y, R);
    this.closePath();
  };
}

const SIZE = 380,
  PAD = 38,
  CELL = (SIZE - PAD * 2) / 4;

function nodePos(n) {
  return [PAD + (n % 5) * CELL, PAD + Math.floor(n / 5) * CELL];
}

function nearest(x, y) {
  let best = -1,
    bestD = Infinity;
  for (let i = 0; i < N; i++) {
    const [nx, ny] = nodePos(i);
    const d = Math.hypot(x - nx, y - ny);
    if (d < bestD) { bestD = d;
      best = i; }
  }
  return bestD < CELL * 0.52 ? best : -1;
}

function easeInOut(t) {
  return t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
}

/* ── Renderer state (inside Board object) ── */
const Board = {
  _canvas: null,
  _ctx: null,
  _board: null,
  _selected: -1,
  _validMoves: [],
  _hoverNode: -1,
  _anim: null,
  _rafId: null,
  _flashNode: -1,
  _flashTimer: null,

  init(canvasId) {
    this._canvas = document.getElementById(canvasId);
    this._ctx = this._canvas.getContext('2d');
  },

  setBoard(board) { this._board = board; },
  setSelected(n) { this._selected = n; },
  setValidMoves(ms) { this._validMoves = ms; },
  setHover(n) { this._hoverNode = n; },

  draw() {
    if (!this._canvas || !this._board) return;
    const ctx = this._ctx;
    ctx.clearRect(0, 0, SIZE, SIZE);
    ctx.fillStyle = '#070b14';
    ctx.beginPath();
    ctx.roundRect(0, 0, SIZE, SIZE, 10);
    ctx.fill();

    // Lines
    const drawn = new Set();
    for (let a = 0; a < N; a++) {
      for (const b of ADJ[a]) {
        const key = [Math.min(a, b), Math.max(a, b)].join('-');
        if (drawn.has(key)) continue;
        drawn.add(key);
        const [ax, ay] = nodePos(a),
          [bx, by] = nodePos(b);
        const isDiag = Math.floor(a / 5) !== Math.floor(b / 5) && (a % 5) !== (b % 5);
        ctx.strokeStyle = isDiag ? 'rgba(61,122,237,.18)' : 'rgba(99,140,210,.35)';
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.moveTo(ax, ay);
        ctx.lineTo(bx, by);
        ctx.stroke();
      }
    }

    // Valid move highlights
    for (const mv of this._validMoves) {
      const [x, y] = nodePos(mv.to);
      const isCap = (mv.capture >= 0);
      ctx.beginPath();
      ctx.arc(x, y, 10, 0, Math.PI * 2);
      ctx.fillStyle = isCap ? 'rgba(232,80,80,.15)' : 'rgba(76,175,110,.15)';
      ctx.fill();
      ctx.strokeStyle = isCap ? 'rgba(232,80,80,.65)' : 'rgba(76,175,110,.65)';
      ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(x, y, 3.5, 0, Math.PI * 2);
      ctx.fillStyle = isCap ? '#e85050' : '#4caf6e';
      ctx.fill();
    }
    for (const mv of this._validMoves) {
      if (mv.capture >= 0) {
        const [cx, cy] = nodePos(mv.capture);
        ctx.beginPath();
        ctx.arc(cx, cy, 13, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(232,80,80,.45)';
        ctx.lineWidth = 1.5;
        ctx.setLineDash([3, 3]);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    }

    // Node dots
    for (let i = 0; i < N; i++) {
      if (this._board[i] && !(this._anim && this._anim.from === i)) continue;
      if (this._anim && this._anim.to === i) continue;
      const [x, y] = nodePos(i);
      ctx.beginPath();
      ctx.arc(x, y, 2.8, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(99,140,210,.38)';
      ctx.fill();
    }

    // Flash
    if (this._flashNode >= 0) {
      const [fx, fy] = nodePos(this._flashNode);
      ctx.beginPath();
      ctx.arc(fx, fy, 16, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(232,80,80,.35)';
      ctx.fill();
    }

    // Static pieces
    for (let i = 0; i < N; i++) {
      if (!this._board[i]) continue;
      if (this._anim && this._anim.from === i) continue;
      this._drawPiece(ctx, ...nodePos(i), this._board[i], i === this._selected);
    }

    // Animated piece
    if (this._anim) {
      const [fx, fy] = nodePos(this._anim.from),
        [tx, ty] = nodePos(this._anim.to);
      const t = easeInOut(this._anim.progress);
      this._drawPiece(ctx, fx + (tx - fx) * t, fy + (ty - fy) * t, this._anim.piece, false);
    }

    // Selection ring
    if (this._selected >= 0 && !this._anim) {
      const [x, y] = nodePos(this._selected);
      ctx.beginPath();
      ctx.arc(x, y, 18, 0, Math.PI * 2);
      ctx.strokeStyle = 'rgba(61,122,237,.4)';
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    // Hover ring
    if (this._hoverNode >= 0 && this._hoverNode !== this._selected && !this._anim) {
      const [x, y] = nodePos(this._hoverNode);
      const hp = this._board[this._hoverNode];
      const isDest = this._validMoves.some(m => m.to === this._hoverNode);
      if (isDest || hp) {
        ctx.beginPath();
        ctx.arc(x, y, 15, 0, Math.PI * 2);
        ctx.strokeStyle = isDest ? 'rgba(76,175,110,.5)' : 'rgba(240,192,64,.35)';
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }
    }
  },

  _drawPiece(ctx, x, y, type, isSel) {
    const isTiger = (type === 'tiger');
    if (isSel) {
      ctx.beginPath();
      ctx.arc(x, y, 16, 0, Math.PI * 2);
      ctx.strokeStyle = '#5b93f5';
      ctx.lineWidth = 2;
      ctx.stroke();
    }
    ctx.beginPath();
    ctx.arc(x, y, 13, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(0,0,0,.35)';
    ctx.fill();
    ctx.beginPath();
    ctx.arc(x, y, 12, 0, Math.PI * 2);
    ctx.fillStyle = isTiger ? (isSel ? '#f07070' : '#e05252') : (isSel ? '#deeaff' : '#c8d8f0');
    ctx.fill();
    ctx.strokeStyle = isTiger ? 'rgba(255,140,140,.45)' : 'rgba(160,190,240,.4)';
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.font = '13px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(isTiger ? '🐯' : '🐐', x, y);
  },

  animateMove(fromNode, toNode, piece, captureNode, onDone) {
    this._anim = { from: fromNode, to: toNode, piece, progress: 0 };
    if (this._rafId) cancelAnimationFrame(this._rafId);
    const DURATION = 260,
      start = performance.now();
    const tick = (now) => {
      this._anim.progress = Math.min((now - start) / DURATION, 1);
      this.draw();
      if (this._anim.progress < 1) {
        this._rafId = requestAnimationFrame(tick);
      } else {
        this._anim = null;
        if (captureNode >= 0) {
          this._flashNode = captureNode;
          this.draw();
          if (this._flashTimer) clearTimeout(this._flashTimer);
          this._flashTimer = setTimeout(() => {
            this._flashNode = -1;
            this.draw();
          }, 400);
        }
        onDone();
      }
    };
    this._rafId = requestAnimationFrame(tick);
  },

  cancelAnim() {
    if (this._rafId) { cancelAnimationFrame(this._rafId);
      this._rafId = null; }
    this._anim = null;
    this._flashNode = -1;
  },

  // Expose helpers for game.js
  ADJ: ADJ,
  nearest: nearest,
  nodePos: nodePos,
  N: N
};

// Make Board globally accessible
window.Board = Board;