#!/usr/bin/env python3
"""Import TWOSIDES pharmacovigilance signals; cross-validate with existing rule-base pairs."""

from __future__ import annotations

import argparse
import csv
import gzip
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils import load_json, normalize_text, save_json

DEFAULT_CSV_CANDIDATES = (
    PROJECT_ROOT / "data" / "TWOSIDES.csv",
    PROJECT_ROOT / "data" / "twosides.csv",
    PROJECT_ROOT / "data" / "external" / "twosides.csv",
    PROJECT_ROOT / "data" / "external" / "TWOSIDES.csv",
    PROJECT_ROOT / "data" / "external" / "TWOSIDES.csv.gz",
)
DEFAULT_INN_MAP = PROJECT_ROOT / "data" / "knowledge" / "drug_inn_map.json"
DEFAULT_RULE_BASE = PROJECT_ROOT / "data" / "knowledge" / "expanded_drug_safety_rules.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "knowledge" / "twosides_ddi_signals.json"

PRR_MIN = 2.0
A_MIN = 3


def resolve_twosides_csv(explicit: Path | None = None) -> Path:
    if explicit is not None:
        if not explicit.exists():
            raise FileNotFoundError(f"TWOSIDES CSV not found: {explicit}")
        return explicit
    for candidate in DEFAULT_CSV_CANDIDATES:
        if candidate.exists():
            return candidate
    searched = ", ".join(str(p) for p in DEFAULT_CSV_CANDIDATES)
    raise FileNotFoundError(
        f"TWOSIDES CSV not found. Place TWOSIDES.csv under data/ or data/external/, or pass --csv. Tried: {searched}"
    )


def _build_inn_lookup(inn_map_path: Path) -> dict[str, str]:
    payload = load_json(inn_map_path)
    mapping = payload.get("map", payload) if isinstance(payload, dict) else {}
    lookup: dict[str, str] = {}
    for key, value in mapping.items():
        canonical = normalize_text(str(value))
        if not canonical:
            continue
        lookup[normalize_text(str(key))] = canonical
        lookup[canonical] = canonical
    return lookup


def _resolve_drug(name: str, lookup: dict[str, str]) -> str:
    normalized = normalize_text(name)
    if not normalized:
        return ""
    if normalized in lookup:
        return lookup[normalized]
    for token in normalized.replace("-", " ").split():
        if token in lookup:
            return lookup[token]
    return ""


def _rule_base_pairs(rule_base_path: Path) -> set[tuple[str, str]]:
    payload = load_json(rule_base_path)
    pairs: set[tuple[str, str]] = set()
    for rule in payload.get("interaction_rules", []):
        drugs = rule.get("drugs", [])
        if len(drugs) >= 2:
            pairs.add(tuple(sorted(normalize_text(d) for d in drugs[:2])))
    return pairs


def _open_csv(path: Path):
    if str(path).endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", errors="replace", newline="")
    return path.open("r", encoding="utf-8", errors="replace", newline="")


def _row_value(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        if key in row and row[key]:
            return str(row[key]).strip()
    lowered = {str(k).lower(): v for k, v in row.items()}
    for key in keys:
        value = lowered.get(key.lower(), "")
        if value:
            return str(value).strip()
    return ""


def import_twosides(
    csv_path: Path,
    inn_map_path: Path,
    rule_base_path: Path,
) -> dict:
    lookup = _build_inn_lookup(inn_map_path)
    known_pairs = _rule_base_pairs(rule_base_path)

    pair_best: dict[tuple[str, str], dict] = {}
    rows_total = 0
    rows_passed = 0

    with _open_csv(csv_path) as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows_total += 1
            try:
                prr = float(_row_value(row, "PRR", "prr") or 0)
                count_a = float(_row_value(row, "A", "a") or 0)
            except ValueError:
                continue
            if prr < PRR_MIN or count_a < A_MIN:
                continue

            drug1 = _resolve_drug(
                _row_value(row, "drug1_name", "Drug1_Name", "drug_1_concept_name", "drug_1_name"),
                lookup,
            )
            drug2 = _resolve_drug(
                _row_value(row, "drug2_name", "Drug2_Name", "drug_2_concept_name", "drug_2_name"),
                lookup,
            )
            if not drug1 or not drug2 or drug1 == drug2:
                continue

            pair = tuple(sorted([drug1, drug2]))
            event_name = _row_value(row, "event_name", "Event_Name", "condition_concept_name", "condition_name")
            rows_passed += 1

            current = pair_best.get(pair)
            score = prr * count_a
            if current and current["_score"] >= score:
                continue

            in_rule_base = pair in known_pairs
            evidence_level = "A" if in_rule_base else "C"
            risk_level = "medium" if in_rule_base else "low"
            pair_best[pair] = {
                "_score": score,
                "rule_id": f"twosides_{pair[0]}_{pair[1]}",
                "drugs": list(pair),
                "risk_level": risk_level,
                "summary": f"TWOSIDES 信号：{pair[0]} 与 {pair[1]} 联用报告 {event_name or '不良事件'}（PRR={prr:.2f}）。",
                "mechanism": f"FAERS 观察性信号：{event_name or 'unknown event'}。",
                "recommendation": "基于自发报告数据，建议评估联用风险并加强监测。",
                "alternatives": ["咨询临床药师。"],
                "clarification_fields": ["current_medications"],
                "source": "twosides_signal",
                "evidence_level": evidence_level,
                "event_name": event_name,
                "prr": prr,
                "report_count": int(count_a),
                "rule_base_validated": in_rule_base,
            }

    signals = []
    for item in pair_best.values():
        item.pop("_score", None)
        signals.append(item)

    return {
        "meta": {
            "source": "twosides",
            "imported_at": datetime.now(timezone.utc).isoformat(),
            "csv_path": str(csv_path),
            "rule_base_path": str(rule_base_path),
            "rows_total": rows_total,
            "rows_passed_filter": rows_passed,
            "unique_pairs": len(signals),
            "rule_base_validated": sum(1 for s in signals if s.get("rule_base_validated")),
            "prr_min": PRR_MIN,
            "a_min": A_MIN,
            "signals": len(signals),
        },
        "signals": signals,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import TWOSIDES DDI signals JSON")
    parser.add_argument("--csv", default="", help="Path to TWOSIDES CSV or CSV.GZ")
    parser.add_argument("--inn-map", default=str(DEFAULT_INN_MAP))
    parser.add_argument("--rule-base", default=str(DEFAULT_RULE_BASE), help="Existing KB for pair cross-validation")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    csv_path = resolve_twosides_csv(Path(args.csv) if args.csv else None)
    payload = import_twosides(csv_path, Path(args.inn_map), Path(args.rule_base))
    save_json(payload, args.output)
    print(f"Wrote {payload['meta']['signals']} TWOSIDES signals -> {args.output}")


if __name__ == "__main__":
    main()
