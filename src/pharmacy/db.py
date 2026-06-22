"""SQLite persistence for pharmacist reviews, decisions, and override audit logs."""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.config import get_config, resolve_path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS pharmacist_reviews (
    review_id TEXT PRIMARY KEY,
    encounter_id TEXT NOT NULL DEFAULT '',
    patient_id TEXT NOT NULL DEFAULT '',
    pharmacist_id TEXT,
    department TEXT NOT NULL DEFAULT '',
    ordering_user_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    reviewed_at TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    cpoe_response_json TEXT NOT NULL,
    max_alert_level TEXT NOT NULL DEFAULT 'info'
);

CREATE INDEX IF NOT EXISTS idx_pharmacist_reviews_status ON pharmacist_reviews(status);
CREATE INDEX IF NOT EXISTS idx_pharmacist_reviews_created ON pharmacist_reviews(created_at);
CREATE INDEX IF NOT EXISTS idx_pharmacist_reviews_patient ON pharmacist_reviews(patient_id);

CREATE TABLE IF NOT EXISTS alert_decisions (
    decision_id TEXT PRIMARY KEY,
    review_id TEXT NOT NULL,
    alert_id TEXT NOT NULL,
    action TEXT NOT NULL,
    override_reason TEXT,
    override_risk_acceptance TEXT,
    pharmacist_notes TEXT,
    decided_at TEXT NOT NULL,
    pharmacist_id TEXT NOT NULL DEFAULT '',
    UNIQUE(review_id, alert_id),
    FOREIGN KEY (review_id) REFERENCES pharmacist_reviews(review_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_alert_decisions_review ON alert_decisions(review_id);

CREATE TABLE IF NOT EXISTS override_audit_logs (
    log_id TEXT PRIMARY KEY,
    review_id TEXT NOT NULL,
    alert_id TEXT NOT NULL,
    order_id TEXT NOT NULL DEFAULT '',
    drug_name TEXT NOT NULL DEFAULT '',
    alert_level TEXT NOT NULL DEFAULT '',
    alert_summary TEXT NOT NULL DEFAULT '',
    pharmacist_id TEXT NOT NULL,
    pharmacist_name TEXT NOT NULL DEFAULT '',
    department TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL,
    override_reason TEXT NOT NULL DEFAULT '',
    risk_acceptance TEXT NOT NULL DEFAULT '',
    timestamp TEXT NOT NULL,
    patient_outcome TEXT,
    supervisor_reviewed INTEGER NOT NULL DEFAULT 0,
    supervisor_id TEXT,
    FOREIGN KEY (review_id) REFERENCES pharmacist_reviews(review_id)
);

CREATE INDEX IF NOT EXISTS idx_override_audit_timestamp ON override_audit_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_override_audit_pharmacist ON override_audit_logs(pharmacist_id);
CREATE INDEX IF NOT EXISTS idx_override_audit_drug ON override_audit_logs(drug_name);
CREATE INDEX IF NOT EXISTS idx_override_audit_level ON override_audit_logs(alert_level);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_db_path() -> Path:
    cfg = get_config()
    rel = cfg.get("pharmacy", {}).get("db_path", "data/pharmacy/pharmacy_reviews.db")
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


def new_review_id() -> str:
    return f"prv_{uuid.uuid4().hex[:12]}"


def new_decision_id() -> str:
    return f"dec_{uuid.uuid4().hex[:12]}"


def new_audit_log_id() -> str:
    return f"aud_{uuid.uuid4().hex[:12]}"
