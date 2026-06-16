# बाघचाल — Baghchal (Python / Flask Edition)

A complete server-authoritative port of the Baghchal board game. **Nothing is
stored in the browser** — no `localStorage`, no client-side game logic beyond
rendering. Every move, every AI decision, and every piece of game state lives
on the Flask server in memory. The browser only sends actions and receives
the resulting board.

## Quick start

```bash
./run.sh
```

This creates a virtualenv, installs Flask, and starts the server at
**http://127.0.0.1:5000**.

Or manually:

```bash
pip install -r requirements.txt
python3 app.py
```

**Demo login:** `admin / admin` (admin role) or `guest / guest` (user role)

## Architecture

```
app.py          — Flask routes (pages + JSON API), the only file that touches HTTP
engine.py        — Pure game logic: board topology, move validation, win/draw detection
ai.py            — Minimax + Alpha-Beta Pruning AI, ported 1:1 from the JS version
auth.py          — In-memory user store: register/login/logout/forgot-password
game_store.py    — In-memory game session store (one entry per active game)
templates/       — Jinja2 HTML (auth.html, game.html, admin.html)
static/css/      — Single stylesheet, shared across all pages
static/js/       — board.js (canvas renderer), game.js (API client + UI controller)
```

### Why server-authoritative?

Every other version of this game (the original HTML/JS build) ran 100% in
the browser: game state lived in a JS object, AI ran in the browser's main
thread, and saves went to `localStorage`. This version inverts that:

- The browser's `game.js` never decides whether a move is legal — it just
  draws what the server says happened, and asks the server "can I do this?"
- All Minimax computation runs in `ai.py` on the server, so a slow client
  device doesn't affect AI strength or speed.
- A user can open the same account on two different browsers and the
  server (not the browser) is the single source of truth for whose turn it is.
- Refreshing the page, closing the tab, or clearing browser data does not
  lose game progress — the game lives in server memory keyed by game ID
  and username.

### What "nothing stored in browser" actually means

- No `localStorage` or `sessionStorage` calls anywhere in the JS.
- The only thing the browser holds onto is a Flask session cookie
  (`HttpOnly`, so JS can't even read it) which maps to a username server-side.
- The board array, move history, captured count, AI difficulty — all of it
  is requested fresh from `/api/game/state` or returned from each action call.

## API reference

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/auth/login` | Login, sets session cookie |
| POST | `/api/auth/register` | Create account, auto-login |
| POST | `/api/auth/logout` | Clear session |
| POST | `/api/auth/forgot` | Generate a 5-minute reset token |
| POST | `/api/auth/reset` | Consume token, set new password |
| POST | `/api/game/new` | Create a game (mode, role, difficulty) |
| GET  | `/api/game/resume` | Fetch the user's active game, if any |
| GET  | `/api/game/state?game_id=` | Fetch current state of a specific game |
| POST | `/api/game/action` | Submit a place/move action — server validates, applies, runs AI reply |
| POST | `/api/game/undo` | Revert to pre-human-move snapshot |
| POST | `/api/game/resign` | Forfeit the game — counts as a loss |
| POST | `/api/game/draw` | Offer / accept / decline a draw |
| GET  | `/api/admin/users` | (admin only) List all users |
| POST | `/api/admin/delete` | (admin only) Delete a non-admin user |

## Game rules (unchanged from the original)

1. 5×5 board, 25 intersections, orthogonal + diagonal lines (diagonals follow
   the `(row+col) % 2 == 0` rule — this gives every corner and the four inner
   hub nodes their correct diagonal edges).
2. 4 tigers start at the corners; 20 goats start off-board.
3. **Phase 1 (Placement):** goats place one piece per turn; tigers move or
   capture each turn.
4. **Phase 2 (Movement):** begins automatically once all 20 goats are placed;
   goats can now move too.
5. **Tiger wins** by capturing 5 goats (jump over an adjacent goat to an
   empty square beyond it, in a straight line).
6. **Goat wins** by trapping all 4 tigers with zero legal moves.
7. **Draw** if goats have no legal moves in Phase 2 (stalemate, not a loss),
   or if the same board position repeats 3 times.
8. **Resign** is available in both phases — the resigning faction loses
   immediately, with a confirmation prompt to prevent misclicks.

## AI

Three difficulty levels, all running server-side:

- **Easy** — pure random legal move selection.
- **Medium** — Minimax, depth 3, Alpha-Beta pruning.
- **Hard** — Minimax, depth 4, Alpha-Beta pruning.

Two distinct heuristics (Tiger: captures + mobility + trap avoidance; Goat:
wall-building + restricting tiger mobility + center control in Phase 1),
ported line-for-line from the original JS `ai.py` module.

## Game modes

- **vs Computer** — choose Tiger or Goat, pick a difficulty. The AI plays
  the opposite faction and responds automatically after every human move
  (the response is computed and returned in the *same* HTTP request).
- **Hotseat** — two players share one device. After every move, a
  "Pass the device" overlay appears showing whose turn is next, so the
  outgoing player can't see the next move before handing over.

## Known limitations of this demo

- User and game data live in plain Python dicts in server memory — restart
  the server and everyone's accounts and games are gone. Swap `auth.py`'s
  `_users` dict and `game_store.py`'s `_games` dict for a real database
  (SQLite, Postgres, Redis) for persistence across restarts.
- Passwords are hashed with SHA-256 and no salt — adequate for a demo, not
  for production. Use `werkzeug.security.generate_password_hash` or `bcrypt`
  in a real deployment.
- The Flask dev server (`app.run()`) is single-process and not meant for
  production traffic. Use `gunicorn` or `waitress` behind a real web server
  for anything beyond local testing.
- The "forgot password" token is returned directly in the API response
  instead of being emailed — there's no email infrastructure in this demo.
