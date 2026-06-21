from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from src.config import get_config, resolve_path
from src.drug_catalog.db import connect, init_schema
from src.drug_catalog.models import HospitalDrug
from src.utils import normalize_text


_CATALOG_SINGLETON: "DrugCatalogService | None" = None


def _row_to_drug(row: sqlite3.Row) -> HospitalDrug:
    alternatives: list[str] = []
    try:
        alternatives = json.loads(row["alternatives_json"] or "[]")
    except json.JSONDecodeError:
        alternatives = []
    return HospitalDrug(
        hospital_drug_id=row["hospital_drug_id"],
        generic_name_cn=row["generic_name_cn"] or "",
        generic_name_en=row["generic_name_en"] or "",
        trade_name_cn=row["trade_name_cn"] or "",
        strength=row["strength"] or "",
        dosage_form=row["dosage_form"] or "",
        route=row["route"] or "",
        atc_code=row["atc_code"] or "",
        rxnorm_rxcui=row["rxnorm_rxcui"] or "",
        insurance_code=row["insurance_code"] or "",
        manufacturer=row["manufacturer"] or "",
        in_formulary=bool(row["in_formulary"]),
        in_stock=bool(row["in_stock"]),
        high_alert=bool(row["high_alert"]),
        antibiotic_level=row["antibiotic_level"] or "",
        narcotic_class=row["narcotic_class"] or "",
        restricted_dept=row["restricted_dept"] or "",
        alternatives=alternatives,
        canonical_key=row["canonical_key"] or "",
        sync_version=row["sync_version"] or "",
    )


class DrugCatalogService:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        conn = connect(self.db_path)
        init_schema(conn)
        conn.close()

    def _query_one(self, sql: str, params: tuple[Any, ...] = ()) -> HospitalDrug | None:
        conn = connect(self.db_path)
        try:
            row = conn.execute(sql, params).fetchone()
            return _row_to_drug(row) if row else None
        finally:
            conn.close()

    def get_by_id(self, hospital_drug_id: str) -> HospitalDrug | None:
        if not hospital_drug_id:
            return None
        return self._query_one(
            "SELECT * FROM hospital_drugs WHERE hospital_drug_id = ?",
            (hospital_drug_id.strip(),),
        )

    def resolve_by_name(self, name: str) -> HospitalDrug | None:
        normalized = normalize_text(name)
        if not normalized:
            return None

        conn = connect(self.db_path)
        try:
            row = conn.execute(
                """
                SELECT d.* FROM drug_aliases a
                JOIN hospital_drugs d ON d.hospital_drug_id = a.hospital_drug_id
                WHERE a.alias_text = ?
                LIMIT 1
                """,
                (normalized,),
            ).fetchone()
            if row:
                return _row_to_drug(row)

            # 子串匹配（商品名/通用名包含）
            row = conn.execute(
                """
                SELECT * FROM hospital_drugs
                WHERE lower(generic_name_cn) LIKE ?
                   OR lower(trade_name_cn) LIKE ?
                   OR lower(generic_name_en) LIKE ?
                ORDER BY length(generic_name_cn) ASC
                LIMIT 1
                """,
                (f"%{normalized}%", f"%{normalized}%", f"%{normalized}%"),
            ).fetchone()
            if row:
                return _row_to_drug(row)

            for alias, canonical in sorted(
                self._fallback_alias_scan(conn, normalized),
                key=lambda item: len(item[0]),
                reverse=True,
            ):
                if alias and alias in normalized:
                    row = conn.execute(
                        "SELECT * FROM hospital_drugs WHERE canonical_key = ? LIMIT 1",
                        (canonical,),
                    ).fetchone()
                    if row:
                        return _row_to_drug(row)
            return None
        finally:
            conn.close()

    @staticmethod
    def _fallback_alias_scan(conn: sqlite3.Connection, normalized: str) -> list[tuple[str, str]]:
        rows = conn.execute("SELECT alias_text, hospital_drug_id FROM drug_aliases").fetchall()
        result: list[tuple[str, str]] = []
        for row in rows:
            drug = conn.execute(
                "SELECT canonical_key FROM hospital_drugs WHERE hospital_drug_id = ?",
                (row["hospital_drug_id"],),
            ).fetchone()
            if drug:
                result.append((row["alias_text"], drug["canonical_key"]))
        return result

    def search(self, query: str, limit: int = 20) -> list[HospitalDrug]:
        normalized = normalize_text(query)
        if not normalized:
            return []
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                """
                SELECT DISTINCT d.* FROM hospital_drugs d
                LEFT JOIN drug_aliases a ON a.hospital_drug_id = d.hospital_drug_id
                WHERE a.alias_text LIKE ?
                   OR lower(d.generic_name_cn) LIKE ?
                   OR lower(d.trade_name_cn) LIKE ?
                   OR lower(d.generic_name_en) LIKE ?
                   OR d.hospital_drug_id LIKE ?
                LIMIT ?
                """,
                (f"%{normalized}%", f"%{normalized}%", f"%{normalized}%", f"%{normalized}%", f"%{query.strip()}%", limit),
            ).fetchall()
            return [_row_to_drug(row) for row in rows]
        finally:
            conn.close()

    def list_alternatives(self, hospital_drug_id: str) -> list[HospitalDrug]:
        drug = self.get_by_id(hospital_drug_id)
        if not drug:
            return []
        resolved: list[HospitalDrug] = []
        for alt in drug.alternatives:
            by_id = self.get_by_id(alt)
            if by_id:
                resolved.append(by_id)
                continue
            by_name = self.resolve_by_name(alt)
            if by_name:
                resolved.append(by_name)
        return resolved

    def stats(self) -> dict[str, Any]:
        conn = connect(self.db_path)
        try:
            total = conn.execute("SELECT COUNT(*) AS c FROM hospital_drugs").fetchone()["c"]
            in_formulary = conn.execute(
                "SELECT COUNT(*) AS c FROM hospital_drugs WHERE in_formulary = 1"
            ).fetchone()["c"]
            in_stock = conn.execute(
                "SELECT COUNT(*) AS c FROM hospital_drugs WHERE in_stock = 1"
            ).fetchone()["c"]
            last_sync = conn.execute(
                """
                SELECT sync_version, finished_at, rows_upserted, source_path, status
                FROM formulary_sync_log
                ORDER BY sync_id DESC LIMIT 1
                """
            ).fetchone()
            return {
                "db_path": str(self.db_path),
                "total_drugs": total,
                "in_formulary": in_formulary,
                "in_stock": in_stock,
                "last_sync": dict(last_sync) if last_sync else None,
            }
        finally:
            conn.close()

    def is_loaded(self) -> bool:
        return self.stats()["total_drugs"] > 0


def get_drug_catalog_service(reload: bool = False) -> DrugCatalogService:
    global _CATALOG_SINGLETON
    if _CATALOG_SINGLETON is not None and not reload:
        return _CATALOG_SINGLETON

    cfg = get_config()
    catalog_cfg = cfg.get("drug_catalog", {})
    db_rel = catalog_cfg.get("db_path", "data/hospital/formulary.db")
    _CATALOG_SINGLETON = DrugCatalogService(resolve_path(db_rel))
    return _CATALOG_SINGLETON


def bootstrap_catalog_from_config() -> dict[str, Any] | None:
    """Import formulary CSV on startup when configured and DB is empty."""
    cfg = get_config()
    catalog_cfg = cfg.get("drug_catalog", {})
    if not catalog_cfg.get("auto_import_on_startup", True):
        return None

    service = get_drug_catalog_service()
    if service.is_loaded():
        return None

    csv_rel = catalog_cfg.get("formulary_path", "data/hospital/formulary_sample.csv")
    csv_path = resolve_path(csv_rel)
    if not csv_path.exists():
        return None

    from src.drug_catalog.csv_import import FormularyCsvImporter

    return FormularyCsvImporter(service.db_path).import_csv(csv_path)
