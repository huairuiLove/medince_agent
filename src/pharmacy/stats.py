"""Pharmacy workload statistics."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.config import get_config, resolve_path
from src.pharmacy.db import connect, default_db_path, init_schema
from src.pharmacy.models import PharmacyStatsResponse

_PHARMACIST_STATS_DDL = """
CREATE TABLE IF NOT EXISTS pharmacist_review_stats (
    user_id TEXT PRIMARY KEY,
    reviews_completed INTEGER NOT NULL DEFAULT 0,
    overrides_count INTEGER NOT NULL DEFAULT 0,
    escalations_count INTEGER NOT NULL DEFAULT 0,
    last_review_at TEXT,
    updated_at TEXT NOT NULL
);
"""


def _auth_db_path() -> Path:
    cfg = get_config()
    rel = cfg.get("auth", {}).get("db_path", "data/auth/medsafe_auth.db")
    return resolve_path(rel)


def _auth_connect() -> sqlite3.Connection:
    path = _auth_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_PHARMACIST_STATS_DDL)
    conn.commit()
    return conn


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PharmacyStatsService:
    def __init__(self, pharmacy_db_path=None, auth_db_path_override=None) -> None:
        self.pharmacy_db_path = pharmacy_db_path or default_db_path()
        self.auth_db_path = auth_db_path_override or _auth_db_path()
        self._conn: sqlite3.Connection | None = None
        self._auth_conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = connect(self.pharmacy_db_path)
            init_schema(self._conn)
        return self._conn

    @property
    def auth_conn(self) -> sqlite3.Connection:
        if self._auth_conn is None:
            self._auth_conn = _auth_connect()
        return self._auth_conn

    def overview(self) -> PharmacyStatsResponse:
        now = _utc_now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        week_start = (now - timedelta(days=7)).isoformat()

        pending_row = self.conn.execute(
            "SELECT COUNT(*) AS c FROM pharmacist_reviews WHERE status = 'pending'",
        ).fetchone()
        pending_count = int(pending_row["c"]) if pending_row else 0

        reviewed_today_row = self.conn.execute(
            """
            SELECT COUNT(*) AS c FROM pharmacist_reviews
            WHERE status = 'reviewed' AND reviewed_at >= ?
            """,
            (today_start,),
        ).fetchone()
        reviewed_today = int(reviewed_today_row["c"]) if reviewed_today_row else 0

        reviewed_week_row = self.conn.execute(
            """
            SELECT COUNT(*) AS c FROM pharmacist_reviews
            WHERE status = 'reviewed' AND reviewed_at >= ?
            """,
            (week_start,),
        ).fetchone()
        reviewed_week = int(reviewed_week_row["c"]) if reviewed_week_row else 0

        total_decisions_row = self.conn.execute(
            "SELECT COUNT(*) AS c FROM alert_decisions WHERE decided_at >= ?",
            (week_start,),
        ).fetchone()
        total_decisions = int(total_decisions_row["c"]) if total_decisions_row else 0

        override_row = self.conn.execute(
            """
            SELECT COUNT(*) AS c FROM override_audit_logs
            WHERE timestamp >= ? AND action = 'override'
            """,
            (week_start,),
        ).fetchone()
        override_count = int(override_row["c"]) if override_row else 0

        high_risk_row = self.conn.execute(
            """
            SELECT COUNT(*) AS c FROM override_audit_logs
            WHERE timestamp >= ? AND action = 'override'
              AND (risk_acceptance = 'high' OR alert_level = 'hard_stop')
            """,
            (week_start,),
        ).fetchone()
        high_risk_overrides = int(high_risk_row["c"]) if high_risk_row else 0

        override_rate = round(override_count / total_decisions, 4) if total_decisions else 0.0
        high_risk_override_rate = round(high_risk_overrides / override_count, 4) if override_count else 0.0

        top_drugs_rows = self.conn.execute(
            """
            SELECT drug_name, COUNT(*) AS cnt
            FROM override_audit_logs
            WHERE timestamp >= ? AND action = 'override' AND drug_name != ''
            GROUP BY drug_name
            ORDER BY cnt DESC
            LIMIT 5
            """,
            (week_start,),
        ).fetchall()
        top_override_drugs = [{"drug_name": r["drug_name"], "count": int(r["cnt"])} for r in top_drugs_rows]

        by_pharmacist_rows = self.auth_conn.execute(
            """
            SELECT user_id, reviews_completed, overrides_count, escalations_count, last_review_at
            FROM pharmacist_review_stats
            ORDER BY reviews_completed DESC
            LIMIT 20
            """,
        ).fetchall()
        by_pharmacist = [
            {
                "user_id": r["user_id"],
                "reviews_completed": int(r["reviews_completed"]),
                "overrides_count": int(r["overrides_count"]),
                "escalations_count": int(r["escalations_count"]),
                "last_review_at": r["last_review_at"],
            }
            for r in by_pharmacist_rows
        ]

        return PharmacyStatsResponse(
            pending_count=pending_count,
            reviewed_today=reviewed_today,
            reviewed_week=reviewed_week,
            override_rate=override_rate,
            high_risk_override_rate=high_risk_override_rate,
            top_override_drugs=top_override_drugs,
            by_pharmacist=by_pharmacist,
        )

    def bump_pharmacist_stats(
        self,
        user_id: str,
        *,
        review_completed: bool = False,
        override: bool = False,
        escalation: bool = False,
    ) -> None:
        now = _utc_now().replace(microsecond=0).isoformat()
        self.auth_conn.execute(
            """
            INSERT INTO pharmacist_review_stats (
                user_id, reviews_completed, overrides_count, escalations_count,
                last_review_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                reviews_completed = pharmacist_review_stats.reviews_completed + excluded.reviews_completed,
                overrides_count = pharmacist_review_stats.overrides_count + excluded.overrides_count,
                escalations_count = pharmacist_review_stats.escalations_count + excluded.escalations_count,
                last_review_at = CASE
                    WHEN excluded.last_review_at IS NOT NULL THEN excluded.last_review_at
                    ELSE pharmacist_review_stats.last_review_at
                END,
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                1 if review_completed else 0,
                1 if override else 0,
                1 if escalation else 0,
                now if review_completed else None,
                now,
            ),
        )
        self.auth_conn.commit()
