#!/usr/bin/env python3
"""Build Stage 11 KB (Stage 9 + department rules) and enrich KG conditions."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_stage9_kb import build_drug_kg_v2, main as stage9_main  # noqa: E402
from src.knowledge_base import DEFAULT_KB_PATH  # noqa: E402
from src.knowledge_mining.kb_merger import merge_all_sources  # noqa: E402
from src.knowledge_mining.stage11_department_rules import get_stage11_rules  # noqa: E402
from src.knowledge_mining.stage11_kg_conditions import merge_condition_nodes  # noqa: E402
from src.knowledge_mining.stage9_curated_rules import get_curated_rules  # noqa: E402
from src.utils import load_json, save_json  # noqa: E402

DEFAULT_EXPANDED = PROJECT_ROOT / "datasets" / "knowledge" / "expanded_drug_safety_rules.json"
DEFAULT_OUTPUT_KB = PROJECT_ROOT / "datasets" / "knowledge" / "hospital_production_v5.json"
DEFAULT_OUTPUT_KG = PROJECT_ROOT / "datasets" / "knowledge" / "drug_kg_v2_stage11.json"
DEFAULT_BASE_KG = PROJECT_ROOT / "datasets" / "knowledge" / "drug_kg.json"


def build_stage11_kb(
    *,
    manual_kb_path: Path = DEFAULT_KB_PATH,
    expanded_path: Path = DEFAULT_EXPANDED,
    twosides_path: Path | None = None,
    output_kb: Path = DEFAULT_OUTPUT_KB,
    output_kg: Path = DEFAULT_OUTPUT_KG,
    base_kg: Path = DEFAULT_BASE_KG,
) -> None:
    if not expanded_path.exists():
        raise FileNotFoundError(f"Expanded KB required: {expanded_path}")

    expanded_kb = load_json(expanded_path)
    curated = get_curated_rules()
    stage11 = get_stage11_rules()
    curated_interactions = list(curated.get("interaction_rules") or [])
    curated_interactions.extend(stage11.get("interaction_rules") or [])
    curated["interaction_rules"] = curated_interactions
    curated.setdefault("meta", {})["stage11_interaction_count"] = len(stage11.get("interaction_rules") or [])

    twosides_payload = load_json(twosides_path) if twosides_path and twosides_path.exists() else None
    merged = merge_all_sources(
        manual_kb_path=manual_kb_path,
        expanded_kb=expanded_kb,
        curated=curated,
        twosides=twosides_payload,
        meta={"version": "hospital_production_v5", "stage": 11},
    )
    save_json(merged, output_kb)

    kg_v2 = build_drug_kg_v2(base_kg, merged)
    kg_v2 = merge_condition_nodes(kg_v2)
    save_json(kg_v2, output_kg)

    meta = merged["meta"]
    print("=== hospital_production_v5 (Stage 11) ===")
    print(f"  interaction_rules: {meta.get('total_interaction_rules', 0)}")
    print(f"  stage11 dept rules: {curated['meta'].get('stage11_interaction_count', 0)}")
    print(f"  KG conditions added: {kg_v2['meta'].get('stage11_conditions_added', 0)}")
    print(f"Wrote KB -> {output_kb}")
    print(f"Wrote KG -> {output_kg}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build Stage 11 knowledge base")
    parser.add_argument("--expanded-kb", default=str(DEFAULT_EXPANDED))
    parser.add_argument("--twosides", default=str(PROJECT_ROOT / "datasets" / "knowledge" / "twosides_ddi_signals.json"))
    parser.add_argument("--without-twosides", action="store_true")
    parser.add_argument("--output-kb", default=str(DEFAULT_OUTPUT_KB))
    parser.add_argument("--output-kg", default=str(DEFAULT_OUTPUT_KG))
    args = parser.parse_args()

    tw_path = None if args.without_twosides else Path(args.twosides)
    build_stage11_kb(
        expanded_path=Path(args.expanded_kb),
        twosides_path=tw_path,
        output_kb=Path(args.output_kb),
        output_kg=Path(args.output_kg),
    )
