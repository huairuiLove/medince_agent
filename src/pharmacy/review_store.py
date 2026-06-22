"""CRUD for pharmacist reviews and alert decisions."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from src.pharmacy.db import (
    _utc_now,
    connect,
    default_db_path,
    init_schema,
    new_decision_id,
    new_review_id,
)
from src.pharmacy.models import AlertDecision, PharmacistReview
from src.schemas import CpoeMedicationReviewResponse

_ALERT_LEVEL_RANK = {"info": 1, "warning": 2, "hard_stop": 3}


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    return datetime.fromisoformat(raw)


def _max_alert_level(cpoe: CpoeMedicationReviewResponse) -> str:
    best = "info"
    best_rank = 0
    for alert in cpoe.alerts:
        rank = _ALERT_LEVEL_RANK.get(alert.alert_level, 0)
        if rank > best_rank:
            best_rank = rank
            best = alert.alert_level
    return best


def _row_to_review(row: sqlite3.Row, decisions: list[AlertDecision]) -> PharmacistReview:
    cpoe = CpoeMedicationReviewResponse.model_validate(json.loads(row["cpoe_response_json"]))
    return PharmacistReview(
        review_id=row["review_id"],
        encounter_id=row["encounter_id"],
        patient_id=row["patient_id"],
        pharmacist_id=row["pharmacist_id"],
        department=row["department"],
        ordering_user_id=row["ordering_user_id"],
        created_at=_parse_dt(row["created_at"]) or datetime.now(timezone.utc),
        reviewed_at=_parse_dt(row["reviewed_at"]),
        status=row["status"],
        cpoe_response=cpoe,
        alert_decisions=decisions,
        max_alert_level=row["max_alert_level"],
    )


class ReviewStore:
    def __init__(self, db_path=None) -> None:
        self.db_path = db_path or default_db_path()
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = connect(self.db_path)
            init_schema(self._conn)
        return self._conn

    def create_review(
        self,
        *,
        encounter_id: str,
        patient_id: str,
        department: str,
        cpoe_response: CpoeMedicationReviewResponse,
        ordering_user_id: str = "",
    ) -> PharmacistReview:
        review_id = new_review_id()
        now = _utc_now()
        max_level = _max_alert_level(cpoe_response)
        self.conn.execute(
            """
            INSERT INTO pharmacist_reviews (
                review_id, encounter_id, patient_id, department, ordering_user_id,
                created_at, status, cpoe_response_json, max_alert_level
            ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                review_id,
                encounter_id,
                patient_id,
                department,
                ordering_user_id,
                now,
                cpoe_response.model_dump_json(),
                max_level,
            ),
        )
        self.conn.commit()
        return self.get_review(review_id)

    def get_review(self, review_id: str) -> PharmacistReview | None:
        row = self.conn.execute(
            "SELECT * FROM pharmacist_reviews WHERE review_id = ?",
            (review_id,),
        ).fetchone()
        if not row:
            return None
        decisions = self._load_decisions(review_id)
        return _row_to_review(row, decisions)

    def _load_decisions(self, review_id: str) -> list[AlertDecision]:
        rows = self.conn.execute(
            """
            SELECT * FROM alert_decisions
            WHERE review_id = ?
            ORDER BY decided_at
            """,
            (review_id,),
        ).fetchall()
        return [
            AlertDecision(
                alert_id=r["alert_id"],
                action=r["action"],
                override_reason=r["override_reason"],
                override_risk_acceptance=r["override_risk_acceptance"],
                pharmacist_notes=r["pharmacist_notes"],
                decided_at=_parse_dt(r["decided_at"]) or datetime.now(timezone.utc),
                pharmacist_id=r["pharmacist_id"],
            )
            for r in rows
        ]

    def upsert_decision(
        self,
        review_id: str,
        decision: AlertDecision,
    ) -> AlertDecision:
        decision_id = new_decision_id()
        decided_at = decision.decided_at.astimezone(timezone.utc).replace(microsecond=0).isoformat()
        self.conn.execute(
            """
            INSERT INTO alert_decisions (
                decision_id, review_id, alert_id, action, override_reason,
                override_risk_acceptance, pharmacist_notes, decided_at, pharmacist_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(review_id, alert_id) DO UPDATE SET
                action = excluded.action,
                override_reason = excluded.override_reason,
                override_risk_acceptance = excluded.override_risk_acceptance,
                pharmacist_notes = excluded.pharmacist_notes,
                decided_at = excluded.decided_at,
                pharmacist_id = excluded.pharmacist_id
            """,
            (
                decision_id,
                review_id,
                decision.alert_id,
                decision.action,
                decision.override_reason,
                decision.override_risk_acceptance,
                decision.pharmacist_notes,
                decided_at,
                decision.pharmacist_id,
            ),
        )
        self.conn.commit()
        return decision

    def mark_reviewed(self, review_id: str, pharmacist_id: str) -> PharmacistReview | None:
        now = _utc_now()
        self.conn.execute(
            """
            UPDATE pharmacist_reviews
            SET status = 'reviewed', reviewed_at = ?, pharmacist_id = ?
            WHERE review_id = ?
            """,
            (now, pharmacist_id, review_id),
        )
        self.conn.commit()
        return self.get_review(review_id)

    def list_pending(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str | None = "pending",
    ) -> tuple[list[sqlite3.Row], int]:
        where = ""
        params: list[object] = []
        if status:
            where = "WHERE status = ?"
            params.append(status)

        total_row = self.conn.execute(
            f"SELECT COUNT(*) AS c FROM pharmacist_reviews {where}",
            params,
        ).fetchone()
        total = int(total_row["c"]) if total_row else 0

        offset = max(page - 1, 0) * page_size
        rows = self.conn.execute(
            f"""
            SELECT * FROM pharmacist_reviews
            {where}
            ORDER BY
                CASE max_alert_level
                    WHEN 'hard_stop' THEN 3
                    WHEN 'warning' THEN 2
                    ELSE 1
                END DESC,
                created_at ASC
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        ).fetchall()
        return rows, total
