from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from src.config import get_config, resolve_path
from src.drug_catalog.atc_taxonomy import build_classification_tree, list_special_filters
from src.drug_catalog.db import connect, init_schema
from src.drug_catalog.models import HospitalDrug
from src.drug_catalog.semantic_search import get_semantic_index, rebuild_semantic_index
from src.llm.errors import DrugSearchModelNotReadyError
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

    def search(
        self,
        query: str,
        limit: int = 20,
        mode: str = "semantic",
    ) -> tuple[list[HospitalDrug], str]:
        """Search formulary. mode: keyword (explicit) | semantic | auto (semantic, no fallback)."""
        normalized = normalize_text(query)
        if not normalized:
            return [], mode

        if mode == "keyword":
            return self._search_keyword(query, limit), "keyword"

        effective_mode = "semantic"
        index = get_semantic_index()
        download_hint = "python scripts/download_models.py --drug-search"

        if not index.model_present:
            raise DrugSearchModelNotReadyError(
                "模型文件缺失",
                f"请运行: {download_hint}",
            )

        status = index.status()
        if status["indexed_drugs"] == 0:
            self._ensure_semantic_index()
            status = index.status()

        if status.get("load_error"):
            raise DrugSearchModelNotReadyError(status["load_error"], download_hint)

        if not status.get("index_built") or status["indexed_drugs"] == 0:
            raise DrugSearchModelNotReadyError(
                "语义索引未构建",
                f"请运行上述命令后 POST /api/v1/drug-catalog/search-model/rebuild",
            )

        semantic_pairs = index.search(query, limit=limit)
        results: list[HospitalDrug] = []
        for drug_id, _score in semantic_pairs:
            drug = self.get_by_id(drug_id)
            if drug:
                results.append(drug)
            if len(results) >= limit:
                break

        return results, effective_mode

    def _search_keyword(self, query: str, limit: int) -> list[HospitalDrug]:
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

    def browse(
        self,
        *,
        atc_prefix: str = "",
        filter_id: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        conn = connect(self.db_path)
        try:
            where: list[str] = []
            params: list[Any] = []

            prefix = (atc_prefix or "").strip().upper()
            if prefix:
                where.append("upper(atc_code) LIKE ?")
                params.append(f"{prefix}%")

            facet = (filter_id or "").strip()
            if facet == "high_alert":
                where.append("high_alert = 1")
            elif facet == "in_stock":
                where.append("in_stock = 1")
            elif facet == "antibiotic":
                where.append("upper(atc_code) LIKE 'J01%'")
            elif facet == "narcotic":
                where.append("(narcotic_class IS NOT NULL AND trim(narcotic_class) != '' AND narcotic_class != '0')")
            elif facet == "restricted":
                where.append("(restricted_dept IS NOT NULL AND trim(restricted_dept) != '')")

            clause = f"WHERE {' AND '.join(where)}" if where else ""
            total = conn.execute(
                f"SELECT COUNT(*) AS c FROM hospital_drugs {clause}",
                tuple(params),
            ).fetchone()["c"]

            rows = conn.execute(
                f"""
                SELECT * FROM hospital_drugs
                {clause}
                ORDER BY generic_name_cn, strength
                LIMIT ? OFFSET ?
                """,
                tuple(params + [limit, offset]),
            ).fetchall()
            return {
                "atc_prefix": prefix,
                "filter_id": facet,
                "total": total,
                "offset": offset,
                "limit": limit,
                "results": [_row_to_drug(row).to_dict() for row in rows],
            }
        finally:
            conn.close()

    def classification_tree(self, max_level: int = 4) -> dict[str, Any]:
        conn = connect(self.db_path)
        try:
            tree = build_classification_tree(conn, max_level=max_level)
            return {
                "max_level": max_level,
                "special_filters": list_special_filters(),
                "tree": tree,
            }
        finally:
            conn.close()

    def search_model_status(self) -> dict[str, Any]:
        index = get_semantic_index()
        status = index.status()
        status["download_command"] = "python scripts/download_models.py --drug-search"
        return status

    def _ensure_semantic_index(self) -> None:
        conn = connect(self.db_path)
        try:
            rows = conn.execute("SELECT * FROM hospital_drugs").fetchall()
            drugs = [_row_to_drug(row) for row in rows]
        finally:
            conn.close()
        rebuild_semantic_index(drugs)

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
        return ensure_semantic_index_if_needed()

    service = get_drug_catalog_service()
    if service.is_loaded():
        return ensure_semantic_index_if_needed()

    csv_rel = catalog_cfg.get("formulary_path", "data/hospital/formulary_sample.csv")
    csv_path = resolve_path(csv_rel)
    if not csv_path.exists():
        return None

    from src.drug_catalog.csv_import import FormularyCsvImporter

    result = FormularyCsvImporter(service.db_path).import_csv(csv_path)
    ensure_semantic_index_if_needed()
    return result


def ensure_semantic_index_if_needed() -> dict[str, Any] | None:
    """Build in-memory semantic index when formulary is loaded but index is missing."""
    import logging

    logger = logging.getLogger("drug-catalog")
    cfg = get_config().get("drug_catalog", {}).get("semantic_search", {})
    if not cfg.get("enabled", True):
        return None

    service = get_drug_catalog_service()
    if not service.is_loaded():
        return None

    index = get_semantic_index()
    status = index.status()
    if status.get("index_built") and status.get("indexed_drugs", 0) > 0:
        return status

    try:
        service._ensure_semantic_index()
        built = get_semantic_index().status()
        logger.info("Drug semantic index ready", extra={"indexed_drugs": built.get("indexed_drugs")})
        return built
    except DrugSearchModelNotReadyError as exc:
        logger.warning("Drug semantic index skipped", extra={"error": str(exc)})
        return None
