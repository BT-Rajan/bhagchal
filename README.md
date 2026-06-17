# Bagh Chal - Tiger and Goat Board Game

A clean, well-organized Flask implementation of the traditional Nepali board game Bagh Chal (बाघचाल).

## Project Structure

```
.
├── app.py               # Main application factory and routes
├── config.py            # Configuration settings
├── analyze.py           # Optional: personality analysis over exported game reports
├── requirements.txt
├── run.sh                # Quick-start script
│
├── models/              # Data layer
│   ├── __init__.py
│   ├── user.py          # User authentication and management
│   └── game.py          # Game session and state storage
│
├── services/            # Business logic layer
│   ├── __init__.py
│   ├── engine.py        # Core game logic (board, moves, validation)
│   ├── ai.py            # Minimax AI with Alpha-Beta pruning
│   └── report.py        # Game report export
│
├── api/                 # REST API routes
│   ├── __init__.py
│   ├── auth.py          # Authentication endpoints
│   └── game.py          # Game action endpoints
│
├── utils/               # Utilities
│   ├── __init__.py
│   └── decorators.py    # Flask route decorators
│
├── templates/           # Jinja2 HTML templates
│   ├── auth.html
│   ├── game.html
│   └── admin.html
│
└── static/              # Static assets
    ├── css/
    │   └── main.css
    └── js/
        ├── board.js
        └── game.js
```

## Key Improvements

### Architecture
- **Separation of Concerns**: Clear separation between models, services, API routes, and utilities
- **Application Factory Pattern**: `create_app()` function for flexible app instantiation
- **Blueprint Organization**: API routes organized into logical blueprints (`auth_bp`, `game_bp`)
- **Dependency Injection**: Services use configuration from centralized config module

### Code Quality
- **Type Hints**: Proper type annotations throughout
- **Docstrings**: Comprehensive documentation for all modules and functions
- **Single Responsibility**: Each class/module has a single, well-defined purpose
- **Testability**: Pure functions in engine module for easy unit testing

### Models Layer
- `UserModel`: Handles all user-related operations (register, login, password reset)
- `SessionStore`: Manages user game sessions
- `GameStore`: Manages individual game instances

### Services Layer
- `GameEngine`: Pure game logic with no external dependencies
- `AIService`: Encapsulated AI logic with configurable difficulty
- `ReportService`: Handles game report generation and export

### API Layer
- Clean RESTful endpoints organized by resource
- Consistent error handling and response format
- Authentication checks via decorators

## Quick Start

```bash
# Quickest: creates a venv, installs deps, and starts the server
./run.sh

# Or manually
pip install -r requirements.txt
python3 app.py

# Or programmatically
from app import create_app
app = create_app()
app.run(debug=True)
```

Open http://127.0.0.1:5000 — demo logins: `admin` / `admin` or `guest` / `guest`.

## API Endpoints

### Authentication
- `POST /api/auth/login` - User login
- `POST /api/auth/register` - Create account
- `POST /api/auth/logout` - Clear session
- `POST /api/auth/forgot` - Generate reset token
- `POST /api/auth/reset` - Reset password

### Game
- `GET /api/game/next` - Get/create next game in session
- `POST /api/game/move` - Submit a move
- `POST /api/game/timer` - Update timer (timed games)
- `POST /api/game/undo` - Undo last move(s)
- `POST /api/game/resign` - Forfeit game
- `POST /api/game/draw` - Offer/accept/decline draw

### Admin
- `GET /api/admin/users` - List all users
- `POST /api/admin/delete` - Delete a user

## Game Rules

1. **Board**: 5×5 grid with orthogonal and diagonal connections
2. **Pieces**: 4 tigers (start at corners) vs 20 goats (off-board initially)
3. **Phase 1**: Goats place one piece per turn; tigers move or capture
4. **Phase 2**: Begins when all 20 goats are placed; both sides move
5. **Tiger wins**: Capture 5 goats by jumping over them
6. **Goat wins**: Trap all 4 tigers with no legal moves
7. **Draw**: Stalemate or 3-time repetition

## AI Difficulty

- **Easy**: Random move selection
- **Medium**: Minimax depth 3 with Alpha-Beta pruning
- **Hard**: Minimax depth 4 with Alpha-Beta pruning

## Session Format

Each user gets a 5-game session with progressive difficulty:
1. Game 1: Play as Tiger vs Easy AI
2. Game 2: Play as Goat vs Easy AI
3. Game 3: Play as Tiger vs Medium AI
4. Game 4: Play as Goat vs Medium AI
5. Game 5: Play as Tiger vs Medium AI (7-minute timed)

## Notes

- **In-Memory Storage**: User and game data is stored in memory (lost on restart)
- **Production Ready**: Swap `_users` and `_games` dicts for a real database
- **Password Hashing**: Uses SHA-256 (upgrade to bcrypt/argon2 for production)
- **Server-Authoritative**: All game logic runs server-side; browser only renders

## Optional: Personality Analysis

`analyze.py` reads an exported game report JSON (saved under `game_reports/` after a game ends) and uses the DeepSeek API to summarize a player's style. It needs a `.env` file with `DEEPSEEK_API_KEY=...` and is run separately from the web app:

```bash
python3 analyze.py game_reports/<report-file>.json
```

## License

MIT License
