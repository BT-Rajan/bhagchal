import sqlite3, os, threading, uuid, hashlib
from contextlib import contextmanager

DB_PATH = os.environ.get('BAGHCHAL_DB', 'baghchal.db')
_local  = threading.local()

def get_conn():
    if not hasattr(_local, 'conn') or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute('PRAGMA journal_mode=WAL')
        _local.conn.execute('PRAGMA foreign_keys=ON')
    return _local.conn

@contextmanager
def tx():
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise

def init_db():
    with tx() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS organizations (
            id         TEXT PRIMARY KEY,
            name       TEXT NOT NULL UNIQUE,
            slug       TEXT NOT NULL UNIQUE,
            plan       TEXT NOT NULL DEFAULT 'trial',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            settings   TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS users (
            id            TEXT PRIMARY KEY,
            org_id        TEXT NOT NULL REFERENCES organizations(id),
            username      TEXT NOT NULL UNIQUE,
            email         TEXT NOT NULL DEFAULT '',
            password_hash TEXT NOT NULL,
            role          TEXT NOT NULL DEFAULT 'user',
            suspended     INTEGER NOT NULL DEFAULT 0,
            created_at    TEXT NOT NULL DEFAULT (datetime('now')),
            last_login    TEXT,
            games_played  INTEGER NOT NULL DEFAULT 0,
            metadata      TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS game_bundles (
            id          TEXT PRIMARY KEY,
            org_id      TEXT NOT NULL REFERENCES organizations(id),
            created_by  TEXT NOT NULL REFERENCES users(id),
            name        TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            depth       INTEGER NOT NULL DEFAULT 3,
            game_count  INTEGER NOT NULL DEFAULT 5,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS bundle_assignments (
            id          TEXT PRIMARY KEY,
            bundle_id   TEXT NOT NULL REFERENCES game_bundles(id),
            assigned_to TEXT NOT NULL REFERENCES users(id),
            assigned_by TEXT NOT NULL REFERENCES users(id),
            assigned_at TEXT NOT NULL DEFAULT (datetime('now')),
            status      TEXT NOT NULL DEFAULT 'pending'
        );

        CREATE TABLE IF NOT EXISTS invites (
            id          TEXT PRIMARY KEY,
            org_id      TEXT NOT NULL REFERENCES organizations(id),
            invited_by  TEXT NOT NULL REFERENCES users(id),
            email       TEXT NOT NULL,
            role        TEXT NOT NULL DEFAULT 'user',
            token       TEXT NOT NULL UNIQUE,
            bundle_id   TEXT REFERENCES game_bundles(id),
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            expires_at  TEXT NOT NULL,
            used        INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id           TEXT PRIMARY KEY,
            user_id      TEXT NOT NULL REFERENCES users(id),
            org_id       TEXT NOT NULL REFERENCES organizations(id),
            bundle_id    TEXT REFERENCES game_bundles(id),
            created_at   TEXT NOT NULL DEFAULT (datetime('now')),
            completed_at TEXT,
            current_game INTEGER NOT NULL DEFAULT 1,
            finished     INTEGER NOT NULL DEFAULT 0,
            metadata     TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS games (
            id           TEXT PRIMARY KEY,
            session_id   TEXT REFERENCES sessions(id),
            user_id      TEXT NOT NULL REFERENCES users(id),
            org_id       TEXT NOT NULL REFERENCES organizations(id),
            game_number  INTEGER,
            mode         TEXT NOT NULL DEFAULT 'ai',
            human_role   TEXT NOT NULL,
            difficulty   TEXT NOT NULL,
            ai_depth     INTEGER NOT NULL DEFAULT 3,
            status       TEXT NOT NULL DEFAULT 'active',
            start_time   TEXT NOT NULL DEFAULT (datetime('now')),
            end_time     TEXT,
            duration_sec REAL,
            time_limit   INTEGER,
            state_json   TEXT NOT NULL DEFAULT '{}',
            move_log_json TEXT NOT NULL DEFAULT '[]',
            created_at   TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS telemetry_events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id    TEXT REFERENCES games(id),
            session_id TEXT REFERENCES sessions(id),
            user_id    TEXT NOT NULL,
            org_id     TEXT NOT NULL,
            event_type TEXT NOT NULL,
            ts         REAL NOT NULL,
            payload    TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS psychometric_profiles (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id            TEXT NOT NULL REFERENCES users(id),
            org_id             TEXT NOT NULL REFERENCES organizations(id),
            session_id         TEXT NOT NULL REFERENCES sessions(id),
            generated_at       TEXT NOT NULL DEFAULT (datetime('now')),
            traits             TEXT,
            decision_style     TEXT,
            strengths          TEXT,
            weaknesses         TEXT,
            temperament        TEXT,
            adaptability       TEXT,
            overall_assessment TEXT,
            match_percentage   INTEGER,
            telemetry_summary  TEXT,
            raw_json           TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_te_game    ON telemetry_events(game_id);
        CREATE INDEX IF NOT EXISTS idx_te_user    ON telemetry_events(user_id);
        CREATE INDEX IF NOT EXISTS idx_te_session ON telemetry_events(session_id);
        CREATE INDEX IF NOT EXISTS idx_te_type    ON telemetry_events(event_type);
        CREATE INDEX IF NOT EXISTS idx_games_user ON games(user_id);
        CREATE INDEX IF NOT EXISTS idx_games_org  ON games(org_id);
        CREATE INDEX IF NOT EXISTS idx_pp_user    ON psychometric_profiles(user_id);
        CREATE INDEX IF NOT EXISTS idx_pp_org     ON psychometric_profiles(org_id);
        CREATE INDEX IF NOT EXISTS idx_ba_user    ON bundle_assignments(assigned_to);
        CREATE INDEX IF NOT EXISTS idx_ba_bundle  ON bundle_assignments(bundle_id);
        CREATE INDEX IF NOT EXISTS idx_inv_token  ON invites(token);
        ''')
    _migrate(get_conn())
    _seed_defaults()

def _migrate(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    if 'suspended' not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN suspended INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    gcols = {r[1] for r in conn.execute("PRAGMA table_info(games)")}
    if 'ai_depth' not in gcols:
        conn.execute("ALTER TABLE games ADD COLUMN ai_depth INTEGER NOT NULL DEFAULT 3")
        conn.commit()
    scols = {r[1] for r in conn.execute("PRAGMA table_info(sessions)")}
    if 'bundle_id' not in scols:
        conn.execute("ALTER TABLE sessions ADD COLUMN bundle_id TEXT REFERENCES game_bundles(id)")
        conn.commit()
    # Seed sponsor account if missing
    import uuid, hashlib
    if not conn.execute("SELECT id FROM users WHERE username='sponsor'").fetchone():
        org = conn.execute("SELECT id FROM organizations LIMIT 1").fetchone()
        if org:
            uid = str(uuid.uuid4())
            ph  = hashlib.sha256(b'sponsor').hexdigest()
            conn.execute(
                "INSERT OR IGNORE INTO users(id,org_id,username,email,password_hash,role) VALUES(?,?,?,?,?,?)",
                (uid, org['id'], 'sponsor', 'sponsor@localhost', ph, 'sponsor'))
            conn.commit()

def _seed_defaults():
    with tx() as conn:
        if conn.execute('SELECT id FROM organizations LIMIT 1').fetchone():
            return
        org_id = str(uuid.uuid4())
        conn.execute("INSERT OR IGNORE INTO organizations(id,name,slug,plan) VALUES(?,?,?,?)",
                     (org_id,'Default Organization','default','enterprise'))
        defaults = [('admin','admin','admin'),('sponsor','sponsor','sponsor'),('guest','guest','user')]
        for username, password, role in defaults:
            uid = str(uuid.uuid4())
            ph  = hashlib.sha256(password.encode()).hexdigest()
            conn.execute(
                "INSERT OR IGNORE INTO users(id,org_id,username,email,password_hash,role) VALUES(?,?,?,?,?,?)",
                (uid, org_id, username, f'{username}@localhost', ph, role))
