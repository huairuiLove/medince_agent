from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from src.config import resolve_path


_ATC_LABELS: dict[str, Any] | None = None

# WHO ATC prefix lengths per hierarchy level (1-indexed)
_ATC_LEVEL_LEN = {1: 1, 2: 3, 3: 4, 4: 5, 5: 7}


def _load_labels() -> dict[str, Any]:
    global _ATC_LABELS
    if _ATC_LABELS is not None:
        return _ATC_LABELS
    path = resolve_path("data/knowledge/atc_classification.json")
    if path.exists():
        with path.open(encoding="utf-8") as fh:
            _ATC_LABELS = json.load(fh)
    else:
        _ATC_LABELS = {"levels": {}}
    return _ATC_LABELS


def _label_for_code(code: str, level: int) -> dict[str, str]:
    labels = _load_labels().get("levels", {})
    level_key = str(level)
    entry = labels.get(level_key, {}).get(code, {})
    if entry:
        return {
            "code": code,
            "name_cn": entry.get("name_cn", code),
            "name_en": entry.get("name_en", code),
        }
    return {"code": code, "name_cn": f"ATC {code}", "name_en": f"ATC {code}"}


def _atc_prefix(atc_code: str, level: int) -> str:
    length = _ATC_LEVEL_LEN.get(level, 1)
    return (atc_code or "").strip()[:length].upper()


def build_classification_tree(conn: sqlite3.Connection, max_level: int = 4) -> list[dict[str, Any]]:
    """Build nested ATC tree with drug counts from hospital_drugs."""
    rows = conn.execute(
        "SELECT atc_code FROM hospital_drugs WHERE atc_code IS NOT NULL AND trim(atc_code) != ''"
    ).fetchall()

    counts: dict[int, dict[str, int]] = {lvl: {} for lvl in range(1, max_level + 1)}
    for row in rows:
        atc = (row["atc_code"] or "").strip().upper()
        if not atc:
            continue
        for lvl in range(1, max_level + 1):
            prefix = _atc_prefix(atc, lvl)
            if len(prefix) < _ATC_LEVEL_LEN[lvl]:
                continue
            counts[lvl][prefix] = counts[lvl].get(prefix, 0) + 1

    def make_node(code: str, level: int) -> dict[str, Any]:
        info = _label_for_code(code, level)
        node: dict[str, Any] = {
            "code": code,
            "level": level,
            "name_cn": info["name_cn"],
            "name_en": info["name_en"],
            "drug_count": counts[level].get(code, 0),
            "children": [],
        }
        if level < max_level:
            child_level = level + 1
            child_len = _ATC_LEVEL_LEN[child_level]
            child_codes = sorted(
                c for c in counts[child_level]
                if c.startswith(code) and len(c) == child_len
            )
            node["children"] = [make_node(c, child_level) for c in child_codes]
        return node

    roots = sorted(counts[1].keys())
    return [make_node(code, 1) for code in roots]


def list_special_filters() -> list[dict[str, str]]:
    """Non-ATC browse facets for clinical pharmacy."""
    return [
        {"id": "high_alert", "name_cn": "高警示药品", "name_en": "High-alert medications"},
        {"id": "in_stock", "name_cn": "有库存", "name_en": "In stock"},
        {"id": "antibiotic", "name_cn": "抗菌药物", "name_en": "Antibiotics (J01)"},
        {"id": "narcotic", "name_cn": "麻醉/精神药品", "name_en": "Narcotic / controlled"},
        {"id": "restricted", "name_cn": "科室限制", "name_en": "Department restricted"},
    ]
