"""SQLite persistence for users, departments, and doctor agent preferences."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.config import get_config, resolve_path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS departments (
    dept_id TEXT PRIMARY KEY,
    name_cn TEXT NOT NULL,
    name_en TEXT NOT NULL DEFAULT '',
    imaging_sources_json TEXT NOT NULL DEFAULT '[]',
    default_models_json TEXT NOT NULL DEFAULT '[]',
    recommended_datasets_json TEXT NOT NULL DEFAULT '[]',
    vision_models_json TEXT NOT NULL DEFAULT '[]',
    nav_routes_json TEXT NOT NULL DEFAULT '[]',
    description TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'doctor',
    dept_id TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (dept_id) REFERENCES departments(dept_id)
);

CREATE INDEX IF NOT EXISTS idx_users_dept ON users(dept_id);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

CREATE TABLE IF NOT EXISTS doctor_agent_prefs (
    user_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (user_id, agent_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS doctor_skill_prefs (
    user_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    skill_id TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (user_id, agent_id, skill_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS doctor_custom_skills (
    skill_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    title TEXT NOT NULL,
    content_md TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_custom_skills_user ON doctor_custom_skills(user_id, agent_id);

CREATE TABLE IF NOT EXISTS pharmacist_review_stats (
    user_id TEXT PRIMARY KEY,
    reviews_completed INTEGER NOT NULL DEFAULT 0,
    overrides_count INTEGER NOT NULL DEFAULT 0,
    escalations_count INTEGER NOT NULL DEFAULT 0,
    last_review_at TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_db_path() -> Path:
    cfg = get_config()
    rel = cfg.get("auth", {}).get("db_path", "data/auth/medsafe_auth.db")
    return resolve_path(rel)


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def new_user_id() -> str:
    return f"usr_{uuid.uuid4().hex[:12]}"


def new_skill_id() -> str:
    return f"csk_{uuid.uuid4().hex[:12]}"


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return dict(row)


def json_loads(raw: str, default: object) -> object:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default
