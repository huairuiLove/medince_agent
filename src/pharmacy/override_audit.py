"""Override audit log persistence and export."""
from __future__ import annotations

import csv
import io
import sqlite3
from datetime import datetime, timezone

from src.pharmacy.db import connect, default_db_path, init_schema, new_audit_log_id
from src.pharmacy.models import AuditListResponse, OverrideAuditLog


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    return datetime.fromisoformat(raw)


def _row_to_log(row: sqlite3.Row) -> OverrideAuditLog:
    return OverrideAuditLog(
        log_id=row["log_id"],
        review_id=row["review_id"],
        alert_id=row["alert_id"],
        order_id=row["order_id"],
        drug_name=row["drug_name"],
        alert_level=row["alert_level"],
        alert_summary=row["alert_summary"],
        pharmacist_id=row["pharmacist_id"],
        pharmacist_name=row["pharmacist_name"],
        department=row["department"],
        action=row["action"],
        override_reason=row["override_reason"],
        risk_acceptance=row["risk_acceptance"],
        timestamp=_parse_dt(row["timestamp"]) or datetime.now(timezone.utc),
        patient_outcome=row["patient_outcome"],
        supervisor_reviewed=bool(row["supervisor_reviewed"]),
        supervisor_id=row["supervisor_id"],
    )


class OverrideAuditStore:
    def __init__(self, db_path=None) -> None:
        self.db_path = db_path or default_db_path()
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = connect(self.db_path)
            init_schema(self._conn)
        return self._conn

    def append_log(self, entry: OverrideAuditLog) -> OverrideAuditLog:
        ts = entry.timestamp.astimezone(timezone.utc).replace(microsecond=0).isoformat()
        self.conn.execute(
            """
            INSERT INTO override_audit_logs (
                log_id, review_id, alert_id, order_id, drug_name, alert_level,
                alert_summary, pharmacist_id, pharmacist_name, department, action,
                override_reason, risk_acceptance, timestamp, patient_outcome,
                supervisor_reviewed, supervisor_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.log_id,
                entry.review_id,
                entry.alert_id,
                entry.order_id,
                entry.drug_name,
                entry.alert_level,
                entry.alert_summary,
                entry.pharmacist_id,
                entry.pharmacist_name,
                entry.department,
                entry.action,
                entry.override_reason,
                entry.risk_acceptance,
                ts,
                entry.patient_outcome,
                1 if entry.supervisor_reviewed else 0,
                entry.supervisor_id,
            ),
        )
        self.conn.commit()
        return entry

    def query_logs(
        self,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        pharmacist_id: str | None = None,
        drug_name: str | None = None,
        alert_level: str | None = None,
        action: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> AuditListResponse:
        clauses: list[str] = []
        params: list[object] = []

        if start_date:
            clauses.append("timestamp >= ?")
            params.append(start_date)
        if end_date:
            clauses.append("timestamp <= ?")
            params.append(end_date)
        if pharmacist_id:
            clauses.append("pharmacist_id = ?")
            params.append(pharmacist_id)
        if drug_name:
            clauses.append("drug_name LIKE ?")
            params.append(f"%{drug_name}%")
        if alert_level:
            clauses.append("alert_level = ?")
            params.append(alert_level)
        if action:
            clauses.append("action = ?")
            params.append(action)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        total_row = self.conn.execute(
            f"SELECT COUNT(*) AS c FROM override_audit_logs {where}",
            params,
        ).fetchone()
        total = int(total_row["c"]) if total_row else 0

        offset = max(page - 1, 0) * page_size
        rows = self.conn.execute(
            f"""
            SELECT * FROM override_audit_logs
            {where}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        ).fetchall()

        return AuditListResponse(
            items=[_row_to_log(r) for r in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    def export_csv(
        self,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        pharmacist_id: str | None = None,
        drug_name: str | None = None,
        alert_level: str | None = None,
        action: str | None = None,
    ) -> str:
        result = self.query_logs(
            start_date=start_date,
            end_date=end_date,
            pharmacist_id=pharmacist_id,
            drug_name=drug_name,
            alert_level=alert_level,
            action=action,
            page=1,
            page_size=100_000,
        )
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow([
            "log_id",
            "timestamp",
            "pharmacist_id",
            "pharmacist_name",
            "department",
            "review_id",
            "alert_id",
            "order_id",
            "drug_name",
            "alert_level",
            "alert_summary",
            "action",
            "override_reason",
            "risk_acceptance",
            "patient_outcome",
            "supervisor_reviewed",
            "supervisor_id",
        ])
        for item in result.items:
            writer.writerow([
                item.log_id,
                item.timestamp.isoformat(),
                item.pharmacist_id,
                item.pharmacist_name,
                item.department,
                item.review_id,
                item.alert_id,
                item.order_id,
                item.drug_name,
                item.alert_level,
                item.alert_summary,
                item.action,
                item.override_reason,
                item.risk_acceptance,
                item.patient_outcome or "",
                "yes" if item.supervisor_reviewed else "no",
                item.supervisor_id or "",
            ])
        return buffer.getvalue()


def make_audit_log(**kwargs) -> OverrideAuditLog:
    return OverrideAuditLog(log_id=new_audit_log_id(), **kwargs)
