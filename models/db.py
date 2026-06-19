import sqlite3
import os
import threading
from contextlib import contextmanager

DB_PATH = os.environ.get('BAGHCHAL_DB', 'baghchal.db')
_local = threading.local()


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
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL UNIQUE,
            slug        TEXT NOT NULL UNIQUE,
            plan        TEXT NOT NULL DEFAULT 'trial',
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            settings    TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS users (
            id              TEXT PRIMARY KEY,
            org_id          TEXT NOT NULL REFERENCES organizations(id),
            username        TEXT NOT NULL UNIQUE,
            email           TEXT NOT NULL DEFAULT '',
            password_hash   TEXT NOT NULL,
            role            TEXT NOT NULL DEFAULT 'user',
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            last_login      TEXT,
            games_played    INTEGER NOT NULL DEFAULT 0,
            metadata        TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id              TEXT PRIMARY KEY,
            user_id         TEXT NOT NULL REFERENCES users(id),
            org_id          TEXT NOT NULL REFERENCES organizations(id),
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            completed_at    TEXT,
            current_game    INTEGER NOT NULL DEFAULT 1,
            finished        INTEGER NOT NULL DEFAULT 0,
            metadata        TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS games (
            id              TEXT PRIMARY KEY,
            session_id      TEXT REFERENCES sessions(id),
            user_id         TEXT NOT NULL REFERENCES users(id),
            org_id          TEXT NOT NULL REFERENCES organizations(id),
            game_number     INTEGER,
            mode            TEXT NOT NULL DEFAULT 'ai',
            human_role      TEXT NOT NULL,
            difficulty      TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'active',
            start_time      TEXT NOT NULL DEFAULT (datetime('now')),
            end_time        TEXT,
            duration_sec    REAL,
            time_limit      INTEGER,
            state_json      TEXT NOT NULL DEFAULT '{}',
            move_log_json   TEXT NOT NULL DEFAULT '[]',
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS telemetry_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id     TEXT REFERENCES games(id),
            session_id  TEXT REFERENCES sessions(id),
            user_id     TEXT NOT NULL,
            org_id      TEXT NOT NULL,
            event_type  TEXT NOT NULL,
            ts          REAL NOT NULL,
            payload     TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS psychometric_profiles (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         TEXT NOT NULL REFERENCES users(id),
            org_id          TEXT NOT NULL REFERENCES organizations(id),
            session_id      TEXT NOT NULL REFERENCES sessions(id),
            generated_at    TEXT NOT NULL DEFAULT (datetime('now')),
            traits          TEXT,
            decision_style  TEXT,
            strengths       TEXT,
            weaknesses      TEXT,
            temperament     TEXT,
            adaptability    TEXT,
            overall_assessment TEXT,
            match_percentage    INTEGER,
            telemetry_summary   TEXT,
            raw_json        TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_te_game     ON telemetry_events(game_id);
        CREATE INDEX IF NOT EXISTS idx_te_user     ON telemetry_events(user_id);
        CREATE INDEX IF NOT EXISTS idx_te_session  ON telemetry_events(session_id);
        CREATE INDEX IF NOT EXISTS idx_te_type     ON telemetry_events(event_type);
        CREATE INDEX IF NOT EXISTS idx_games_user  ON games(user_id);
        CREATE INDEX IF NOT EXISTS idx_games_org   ON games(org_id);
        CREATE INDEX IF NOT EXISTS idx_pp_user     ON psychometric_profiles(user_id);
        CREATE INDEX IF NOT EXISTS idx_pp_org      ON psychometric_profiles(org_id);
        ''')
    _seed_defaults()


def _seed_defaults():
    with tx() as conn:
        existing = conn.execute('SELECT id FROM organizations LIMIT 1').fetchone()
        if existing:
            return
        import uuid, hashlib, time
        org_id = str(uuid.uuid4())
        conn.execute(
            "INSERT OR IGNORE INTO organizations(id,name,slug,plan) VALUES(?,?,?,?)",
            (org_id, 'Default Organization', 'default', 'enterprise')
        )
        for username, password, role in [('admin','admin','admin'),('guest','guest','user')]:
            uid = str(uuid.uuid4())
            ph  = hashlib.sha256(password.encode()).hexdigest()
            conn.execute(
                "INSERT OR IGNORE INTO users(id,org_id,username,email,password_hash,role) VALUES(?,?,?,?,?,?)",
                (uid, org_id, username, f'{username}@localhost', ph, role)
            )
