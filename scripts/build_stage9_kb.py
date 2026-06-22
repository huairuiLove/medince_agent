#!/usr/bin/env python3
"""Build Stage 9 hospital_production_v4 knowledge base and drug_kg_v2."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.knowledge_base import DEFAULT_KB_PATH
from src.knowledge_mining.kg_enrichment import enrich_knowledge_graph
from src.knowledge_mining.kb_merger import merge_all_sources
from src.knowledge_mining.stage9_curated_rules import get_curated_rules
from src.utils import load_json, normalize_text, save_json

DEFAULT_EXPANDED = PROJECT_ROOT / "data" / "knowledge" / "expanded_drug_safety_rules.json"
DEFAULT_TWOSIDES = PROJECT_ROOT / "data" / "knowledge" / "twosides_ddi_signals.json"
DEFAULT_KG = PROJECT_ROOT / "data" / "knowledge" / "drug_kg.json"
DEFAULT_OUTPUT_KB = PROJECT_ROOT / "data" / "knowledge" / "hospital_production_v4.json"
DEFAULT_OUTPUT_KG = PROJECT_ROOT / "data" / "knowledge" / "drug_kg_v2.json"

RISK_TO_SEVERITY = {
    "high": "severe",
    "medium": "moderate",
    "low": "mild",
    "none": "mild",
    "unknown": "moderate",
}


def _drug_node_id(canonical: str) -> str:
    slug = normalize_text(canonical).replace(" ", "_").replace("-", "_")
    return f"d_{slug}"


def _ensure_nodes(nodes: list[dict], node_ids: set[str], drug_names: set[str]) -> None:
    existing_names = {normalize_text(node.get("name", "")) for node in nodes if node.get("type") == "Drug"}
    for drug in sorted(drug_names):
        canonical = normalize_text(drug)
        if not canonical or canonical in existing_names:
            continue
        node_id = _drug_node_id(canonical)
        if node_id in node_ids:
            continue
        nodes.append(
            {
                "id": node_id,
                "type": "Drug",
                "name": canonical,
                "brand_names": [],
                "atc_code": "",
                "category": "",
                "rx_type": "Rx",
                "description": f"Stage 9 KB auto-added node for {canonical}",
            }
        )
        node_ids.add(node_id)
        existing_names.add(canonical)


def _normalize_risk_level(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value:
        first = value[0]
        return first if isinstance(first, str) else "medium"
    return "medium"


def build_drug_kg_v2(base_kg_path: Path, merged_kb: dict) -> dict:
    base = load_json(base_kg_path)
    nodes: list[dict] = list(base.get("nodes", []))
    edges: list[dict] = list(base.get("edges", []))
    node_ids = {node["id"] for node in nodes}
    edge_keys = {(edge["source"], edge["target"], edge["type"]) for edge in edges}

    drug_names: set[str] = set()
    for rule in merged_kb.get("interaction_rules", []):
        drug_names.update(rule.get("drugs", []))
    for rule in merged_kb.get("population_rules", []):
        drug_names.update(rule.get("trigger_drugs", []))
    for rule in merged_kb.get("allergy_rules", []):
        drug_names.update(rule.get("trigger_drugs", []))

    _ensure_nodes(nodes, node_ids, drug_names)

    name_to_id = {}
    for node in nodes:
        if node.get("type") == "Drug":
            name_to_id[normalize_text(node.get("name", ""))] = node["id"]
            name_to_id[normalize_text(node["id"].replace("d_", "").replace("_", " "))] = node["id"]

    for rule in merged_kb.get("interaction_rules", []):
        drugs = rule.get("drugs", [])
        if len(drugs) < 2:
            continue
        source_id = name_to_id.get(normalize_text(drugs[0])) or _drug_node_id(drugs[0])
        target_id = name_to_id.get(normalize_text(drugs[1])) or _drug_node_id(drugs[1])
        key = (source_id, target_id, "INTERACTS_WITH")
        if key in edge_keys:
            continue
        edges.append(
            {
                "source": source_id,
                "target": target_id,
                "type": "INTERACTS_WITH",
                "severity": RISK_TO_SEVERITY.get(_normalize_risk_level(rule.get("risk_level")), "moderate"),
                "mechanism": rule.get("mechanism", ""),
                "effect": rule.get("summary", ""),
                "recommendation": rule.get("recommendation", ""),
                "evidence_level": rule.get("evidence_level", rule.get("source", "B")[:1].upper()),
                "rule_id": rule.get("rule_id", ""),
            }
        )
        edge_keys.add(key)

    pop_node_map = {
        "pregnancy_status": "pop_pregnant",
        "lactation": "pop_lactating",
        "age": "pop_elderly",
        "egfr": "pop_kidney_impaired",
        "hepatic": "pop_liver_impaired",
    }
    pop_ids = {node["id"]: node for node in nodes if node.get("type") == "Population"}

    for rule in merged_kb.get("population_rules", []):
        field = rule.get("population_field", "")
        pop_id = pop_node_map.get(field, "pop_kidney_impaired" if field == "egfr" else "")
        if not pop_id or pop_id not in pop_ids:
            continue
        for drug in rule.get("trigger_drugs", []):
            drug_id = name_to_id.get(normalize_text(drug)) or _drug_node_id(drug)
            key = (drug_id, pop_id, "CONTRAINDICATED_FOR")
            if key in edge_keys:
                continue
            edges.append(
                {
                    "source": drug_id,
                    "target": pop_id,
                    "type": "CONTRAINDICATED_FOR",
                    "severity": RISK_TO_SEVERITY.get(_normalize_risk_level(rule.get("risk_level")), "severe"),
                    "mechanism": rule.get("mechanism", ""),
                    "effect": rule.get("summary", ""),
                    "recommendation": rule.get("recommendation", ""),
                    "evidence_level": "A",
                    "rule_id": rule.get("rule_id", ""),
                }
            )
            edge_keys.add(key)

    meta = dict(base.get("meta", {}))
    meta.update(
        {
            "version": "2.0.0",
            "description": "Drug knowledge graph v2 expanded from hospital_production_v4 rules",
            "last_updated": datetime.now(timezone.utc).date().isoformat(),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "source_kb": "hospital_production_v4",
        }
    )
    base_kg = {"meta": meta, "nodes": nodes, "edges": edges}
    return enrich_knowledge_graph(base_kg, merged_kb)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Stage 9 hospital_production_v4 knowledge base")
    parser.add_argument("--manual-kb", default=str(DEFAULT_KB_PATH))
    parser.add_argument("--expanded-kb", default=str(DEFAULT_EXPANDED))
    parser.add_argument("--twosides", default=str(DEFAULT_TWOSIDES))
    parser.add_argument("--base-kg", default=str(DEFAULT_KG))
    parser.add_argument("--output-kb", default=str(DEFAULT_OUTPUT_KB))
    parser.add_argument("--output-kg", default=str(DEFAULT_OUTPUT_KG))
    parser.add_argument(
        "--without-twosides",
        action="store_true",
        help="Build without TWOSIDES layer (skip import until CSV is available)",
    )
    parser.add_argument(
        "--import-twosides",
        action="store_true",
        help="Run TWOSIDES importer (requires data/external/twosides.csv or TWOSIDES.csv.gz)",
    )
    parser.add_argument("--twosides-csv", default="", help="Explicit TWOSIDES CSV path for --import-twosides")
    args = parser.parse_args()

    expanded_path = Path(args.expanded_kb)
    if not expanded_path.exists():
        raise FileNotFoundError(f"Expanded KB required: {expanded_path}")

    twosides_path = Path(args.twosides)
    twosides_payload: dict | None
    if args.without_twosides:
        twosides_payload = None
    elif args.import_twosides:
        from scripts.import_twosides import import_twosides, resolve_twosides_csv

        csv_path = resolve_twosides_csv(Path(args.twosides_csv) if args.twosides_csv else None)
        twosides_payload = import_twosides(
            csv_path,
            PROJECT_ROOT / "data" / "knowledge" / "drug_inn_map.json",
            expanded_path,
        )
        save_json(twosides_payload, twosides_path)
    elif not twosides_path.exists():
        raise FileNotFoundError(
            f"TWOSIDES signals not found at {twosides_path}. "
            "Run with --import-twosides after placing twosides.csv under data/external/."
        )
    else:
        twosides_payload = load_json(twosides_path)

    expanded_kb = load_json(expanded_path)
    curated = get_curated_rules()

    merged = merge_all_sources(
        manual_kb_path=args.manual_kb,
        expanded_kb=expanded_kb,
        curated=curated,
        twosides=twosides_payload,
    )

    save_json(merged, args.output_kb)
    kg_v2 = build_drug_kg_v2(Path(args.base_kg), merged)
    save_json(kg_v2, args.output_kg)

    meta = merged["meta"]
    print("=== hospital_production_v4 rule counts ===")
    print(f"  interaction_rules:      {meta.get('total_interaction_rules', 0)}")
    print(f"    curated added:        {meta.get('curated_interaction_added', 0)}")
    print(f"    twosides added:       {meta.get('twosides_interaction_added', 0)}")
    print(f"    twosides upgraded:    {meta.get('twosides_pairs_upgraded', 0)}")
    print(f"  population_rules:       {meta.get('population_rules', 0)} (+{meta.get('population_rules_added', 0)} curated)")
    print(f"  allergy_rules:          {meta.get('allergy_rules', 0)} (+{meta.get('allergy_rules_added', 0)} curated)")
    print(f"  scenario_rules:         {meta.get('scenario_rules', 0)} (+{meta.get('scenario_rules_added', 0)} curated)")
    print(f"  duplicate_rules:        {meta.get('duplicate_rules', 0)}")
    print(f"  drug_kg_v2 nodes:       {kg_v2['meta'].get('node_count', len(kg_v2['nodes']))}")
    print(f"  drug_kg_v2 edges:       {kg_v2['meta'].get('edge_count', len(kg_v2['edges']))}")
    print(f"Wrote KB  -> {args.output_kb}")
    print(f"Wrote KG  -> {args.output_kg}")


if __name__ == "__main__":
    main()
