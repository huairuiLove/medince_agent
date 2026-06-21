from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from src.drug_catalog.db import connect, init_schema
from src.utils import normalize_text, utc_now_iso


# PIS 导出 CSV 列名（中英文表头均支持）
CSV_COLUMN_ALIASES: dict[str, list[str]] = {
    "hospital_drug_id": ["hospital_drug_id", "drug_id", "院内药品码", "药品编码", "drug_code"],
    "generic_name_cn": ["generic_name_cn", "generic_name", "通用名", "药品通用名"],
    "generic_name_en": ["generic_name_en", "generic_name_en_us", "英文通用名", "inn_name"],
    "trade_name_cn": ["trade_name_cn", "trade_name", "商品名", "药品商品名"],
    "strength": ["strength", "spec", "规格", "剂量规格"],
    "dosage_form": ["dosage_form", "form", "剂型"],
    "route": ["route", "admin_route", "给药途径", "用法"],
    "atc_code": ["atc_code", "atc", "ATC编码"],
    "rxnorm_rxcui": ["rxnorm_rxcui", "rxcui", "rxnorm", "RxNorm"],
    "insurance_code": ["insurance_code", "医保编码", "nhs_code", "国家医保编码"],
    "manufacturer": ["manufacturer", "厂家", "生产企业"],
    "in_formulary": ["in_formulary", "formulary", "目录内", "是否在院目录"],
    "in_stock": ["in_stock", "stock", "有库存", "库存状态"],
    "high_alert": ["high_alert", "高警示", "高警示药品"],
    "antibiotic_level": ["antibiotic_level", "抗菌药物级别", "antibiotic_class"],
    "narcotic_class": ["narcotic_class", "麻精分类", "管制分类"],
    "restricted_dept": ["restricted_dept", "限制科室", "dept_restriction"],
    "alternatives": ["alternatives", "替代药", "substitutes", "替代品种"],
}


def _parse_bool(value: Any, default: bool = True) -> bool:
    if value is None or str(value).strip() == "":
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "是", "有", "在目录", "在库"}:
        return True
    if text in {"0", "false", "no", "n", "否", "无", "缺货", "不在目录"}:
        return False
    return default


def _parse_alternatives(value: Any) -> list[str]:
    if not value or str(value).strip() == "":
        return []
    text = str(value).strip()
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except json.JSONDecodeError:
            pass
    for sep in ("|", ";", "、"):
        if sep in text:
            return [part.strip() for part in text.split(sep) if part.strip()]
    if "," in text:
        return [part.strip() for part in text.split(",") if part.strip()]
    return [text]


def _normalize_header(header: str) -> str:
    return re.sub(r"\s+", "", header.strip().lower())


def _map_csv_headers(fieldnames: list[str] | None) -> dict[str, str]:
    if not fieldnames:
        raise ValueError("CSV 文件缺少表头行")
    normalized = {_normalize_header(name): name for name in fieldnames if name}
    mapping: dict[str, str] = {}
    for canonical, aliases in CSV_COLUMN_ALIASES.items():
        for alias in aliases:
            key = _normalize_header(alias)
            if key in normalized:
                mapping[canonical] = normalized[key]
                break
    if "hospital_drug_id" not in mapping:
        raise ValueError(
            "CSV 必须包含 hospital_drug_id（或 院内药品码/药品编码）列。"
            f" 当前表头: {fieldnames}"
        )
    return mapping


def derive_canonical_key(generic_name_en: str, generic_name_cn: str, rxnorm_rxcui: str) -> str:
    if generic_name_en.strip():
        return normalize_text(generic_name_en)
    # 中文通用名 → 尝试从 knowledge base 常见映射；否则用 normalize 后的中文
    cn = normalize_text(generic_name_cn)
    cn_to_en = {
        "华法林": "warfarin",
        "华法林钠": "warfarin",
        "阿司匹林": "aspirin",
        "布洛芬": "ibuprofen",
        "对乙酰氨基酚": "acetaminophen",
        "阿莫西林": "amoxicillin",
        "氨苄西林": "ampicillin",
        "青霉素": "penicillin",
        "赖诺普利": "lisinopril",
        "氯沙坦": "losartan",
        "克拉霉素": "clarithromycin",
        "辛伐他汀": "simvastatin",
        "肝素": "heparin",
        "依诺肝素": "enoxaparin",
        "阿托伐他汀": "atorvastatin",
        "氯吡格雷": "clopidogrel",
        "二甲双胍": "metformin",
        "奥美拉唑": "omeprazole",
    }
    for key, en in cn_to_en.items():
        if key in generic_name_cn or cn == normalize_text(key):
            return en
    if rxnorm_rxcui:
        return f"rxnorm_{rxnorm_rxcui}"
    return cn


def _alias_candidates(drug_row: dict[str, Any]) -> list[tuple[str, str]]:
    aliases: list[tuple[str, str]] = []
    hid = drug_row["hospital_drug_id"]

    def add(text: str, alias_type: str) -> None:
        norm = normalize_text(text)
        if norm:
            aliases.append((norm, alias_type))

    add(drug_row.get("generic_name_cn", ""), "generic_cn")
    add(drug_row.get("generic_name_en", ""), "generic_en")
    add(drug_row.get("trade_name_cn", ""), "trade")
    add(drug_row.get("canonical_key", ""), "canonical")
    strength = drug_row.get("strength", "")
    if drug_row.get("generic_name_cn") and strength:
        add(f"{drug_row['generic_name_cn']} {strength}", "generic_spec")
    if drug_row.get("trade_name_cn") and strength:
        add(f"{drug_row['trade_name_cn']} {strength}", "trade_spec")
    return aliases


class FormularyCsvImporter:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def import_csv(
        self,
        csv_path: str | Path,
        sync_version: str | None = None,
        encoding: str = "utf-8-sig",
    ) -> dict[str, Any]:
        csv_path = Path(csv_path)
        if not csv_path.exists():
            raise FileNotFoundError(f"Formulary CSV not found: {csv_path}")

        version = sync_version or utc_now_iso()
        started = utc_now_iso()
        conn = connect(self.db_path)
        init_schema(conn)

        sync_id = conn.execute(
            """
            INSERT INTO formulary_sync_log (source_path, sync_version, started_at, status)
            VALUES (?, ?, ?, 'running')
            """,
            (str(csv_path), version, started),
        ).lastrowid

        rows_total = 0
        rows_upserted = 0
        try:
            with csv_path.open("r", encoding=encoding, newline="") as handle:
                reader = csv.DictReader(handle)
                header_map = _map_csv_headers(reader.fieldnames)

                for raw_row in reader:
                    rows_total += 1
                    row = {canonical: (raw_row.get(src_col) or "").strip() for canonical, src_col in header_map.items()}

                    hospital_drug_id = row.get("hospital_drug_id", "").strip()
                    if not hospital_drug_id:
                        continue

                    generic_name_cn = row.get("generic_name_cn", "")
                    generic_name_en = row.get("generic_name_en", "")
                    rxnorm = row.get("rxnorm_rxcui", "")
                    canonical_key = derive_canonical_key(generic_name_en, generic_name_cn, rxnorm)

                    drug_row = {
                        "hospital_drug_id": hospital_drug_id,
                        "generic_name_cn": generic_name_cn,
                        "generic_name_en": generic_name_en,
                        "trade_name_cn": row.get("trade_name_cn", ""),
                        "strength": row.get("strength", ""),
                        "dosage_form": row.get("dosage_form", ""),
                        "route": row.get("route", ""),
                        "atc_code": row.get("atc_code", ""),
                        "rxnorm_rxcui": rxnorm,
                        "insurance_code": row.get("insurance_code", ""),
                        "manufacturer": row.get("manufacturer", ""),
                        "in_formulary": _parse_bool(row.get("in_formulary"), True),
                        "in_stock": _parse_bool(row.get("in_stock"), True),
                        "high_alert": _parse_bool(row.get("high_alert"), False),
                        "antibiotic_level": row.get("antibiotic_level", ""),
                        "narcotic_class": row.get("narcotic_class", ""),
                        "restricted_dept": row.get("restricted_dept", ""),
                        "alternatives_json": json.dumps(_parse_alternatives(row.get("alternatives", "")), ensure_ascii=False),
                        "canonical_key": canonical_key,
                        "sync_version": version,
                        "updated_at": utc_now_iso(),
                    }

                    conn.execute(
                        """
                        INSERT INTO hospital_drugs (
                            hospital_drug_id, generic_name_cn, generic_name_en, trade_name_cn,
                            strength, dosage_form, route, atc_code, rxnorm_rxcui, insurance_code,
                            manufacturer, in_formulary, in_stock, high_alert, antibiotic_level,
                            narcotic_class, restricted_dept, alternatives_json, canonical_key,
                            sync_version, updated_at
                        ) VALUES (
                            :hospital_drug_id, :generic_name_cn, :generic_name_en, :trade_name_cn,
                            :strength, :dosage_form, :route, :atc_code, :rxnorm_rxcui, :insurance_code,
                            :manufacturer, :in_formulary, :in_stock, :high_alert, :antibiotic_level,
                            :narcotic_class, :restricted_dept, :alternatives_json, :canonical_key,
                            :sync_version, :updated_at
                        )
                        ON CONFLICT(hospital_drug_id) DO UPDATE SET
                            generic_name_cn=excluded.generic_name_cn,
                            generic_name_en=excluded.generic_name_en,
                            trade_name_cn=excluded.trade_name_cn,
                            strength=excluded.strength,
                            dosage_form=excluded.dosage_form,
                            route=excluded.route,
                            atc_code=excluded.atc_code,
                            rxnorm_rxcui=excluded.rxnorm_rxcui,
                            insurance_code=excluded.insurance_code,
                            manufacturer=excluded.manufacturer,
                            in_formulary=excluded.in_formulary,
                            in_stock=excluded.in_stock,
                            high_alert=excluded.high_alert,
                            antibiotic_level=excluded.antibiotic_level,
                            narcotic_class=excluded.narcotic_class,
                            restricted_dept=excluded.restricted_dept,
                            alternatives_json=excluded.alternatives_json,
                            canonical_key=excluded.canonical_key,
                            sync_version=excluded.sync_version,
                            updated_at=excluded.updated_at
                        """,
                        {
                            **drug_row,
                            "in_formulary": int(drug_row["in_formulary"]),
                            "in_stock": int(drug_row["in_stock"]),
                            "high_alert": int(drug_row["high_alert"]),
                        },
                    )

                    conn.execute(
                        "DELETE FROM drug_aliases WHERE hospital_drug_id = ?",
                        (hospital_drug_id,),
                    )
                    seen_aliases: set[str] = set()
                    for alias_text, alias_type in _alias_candidates({**drug_row, **row, "canonical_key": canonical_key}):
                        if alias_text in seen_aliases:
                            continue
                        seen_aliases.add(alias_text)
                        conn.execute(
                            "INSERT OR IGNORE INTO drug_aliases (alias_text, hospital_drug_id, alias_type) VALUES (?, ?, ?)",
                            (alias_text, hospital_drug_id, alias_type),
                        )

                    rows_upserted += 1

            finished = utc_now_iso()
            conn.execute(
                """
                UPDATE formulary_sync_log
                SET rows_total=?, rows_upserted=?, finished_at=?, status='success'
                WHERE sync_id=?
                """,
                (rows_total, rows_upserted, finished, sync_id),
            )
            conn.commit()
            return {
                "sync_id": sync_id,
                "source_path": str(csv_path),
                "sync_version": version,
                "rows_total": rows_total,
                "rows_upserted": rows_upserted,
                "status": "success",
            }
        except Exception as exc:
            conn.execute(
                """
                UPDATE formulary_sync_log
                SET rows_total=?, rows_upserted=?, finished_at=?, status='failed', error_message=?
                WHERE sync_id=?
                """,
                (rows_total, rows_upserted, utc_now_iso(), str(exc), sync_id),
            )
            conn.commit()
            raise
        finally:
            conn.close()
