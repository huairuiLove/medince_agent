#!/usr/bin/env python3
"""Mine DDI rules with Bio_ClinicalBERT and merge into expanded knowledge base.

Example:
  python scripts/mine_ddi_rules.py --max-drugs 120 --warm-smiles
  python scripts/mine_ddi_rules.py --max-drugs 0  # full universe (~85k pairs, slow on CPU)
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_config, resolve_path
from src.knowledge_base import DEFAULT_KB_PATH
from src.knowledge_mining.ddi_miner import DdiRuleMiner
from src.knowledge_mining.duplicate_miner import mine_duplicate_rules
from src.knowledge_mining.drug_universe import build_alias_map_from_inn
from src.knowledge_mining.kb_merger import merge_knowledge_base
from src.safety_models.smiles_lookup import SmilesLookup
from src.utils import save_json, write_jsonl


def warm_smiles(drugs: list[str], allow_network: bool) -> tuple[int, int]:
    lookup = SmilesLookup()
    ok = 0
    for drug in drugs:
        if lookup.resolve(drug, allow_network=allow_network):
            ok += 1
    return ok, len(drugs)


def main() -> None:
    parser = argparse.ArgumentParser(description="Mine DDI rules and build expanded knowledge base")
    parser.add_argument("--manual-kb", default=str(DEFAULT_KB_PATH), help="Curated minimal rules JSON")
    parser.add_argument(
        "--output",
        default="datasets/knowledge/expanded_drug_safety_rules.json",
        help="Merged knowledge base output",
    )
    parser.add_argument(
        "--mined-only",
        default="datasets/knowledge/mined_ddi_rules.json",
        help="Raw mined DDI rules (no manual merge)",
    )
    parser.add_argument(
        "--scores-jsonl",
        default="datasets/knowledge/mined_ddi_scores.jsonl",
        help="All positive pair scores for audit",
    )
    parser.add_argument("--inn-map", default="datasets/knowledge/drug_inn_map.json")
    parser.add_argument("--formulary", default="datasets/hospital/formulary_demo.csv")
    parser.add_argument(
        "--max-drugs",
        type=int,
        default=150,
        help="Cap drug universe size (0 = no cap)",
    )
    parser.add_argument(
        "--max-pairs",
        type=int,
        default=0,
        help="Cap pair count for smoke tests (0 = all pairs)",
    )
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--high-threshold", type=float, default=None, help="Override DDI high threshold")
    parser.add_argument("--medium-threshold", type=float, default=None, help="Override DDI medium threshold")
    parser.add_argument("--warm-smiles", action="store_true", help="Resolve SMILES before mining")
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="Allow PubChem lookup when warming SMILES",
    )
    parser.add_argument(
        "--exclusions",
        default="datasets/knowledge/ddi_mining_exclusions.json",
        help="Pair/drug exclusion list for mining",
    )
    parser.add_argument(
        "--update-config",
        action="store_true",
        help="Point config.yaml data.knowledge_base to merged output",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    load_config()
    max_drugs = None if args.max_drugs <= 0 else args.max_drugs
    max_pairs = None if args.max_pairs <= 0 else args.max_pairs

    cfg = load_config()
    mining_cfg = cfg.get("clinical_knowledge", {}).get("mining_thresholds", {})
    if args.high_threshold is None and mining_cfg.get("high") is not None:
        args.high_threshold = float(mining_cfg["high"])
    if args.medium_threshold is None and mining_cfg.get("medium") is not None:
        args.medium_threshold = float(mining_cfg["medium"])

    from src.knowledge_mining.drug_universe import collect_canonical_drugs

    universe = collect_canonical_drugs(
        inn_map_path=args.inn_map,
        formulary_path=args.formulary,
        max_drugs=max_drugs,
    )
    if args.warm_smiles:
        logging.info("Warming SMILES for %d drugs...", len(universe))
        ok, total = warm_smiles(universe, allow_network=args.allow_network)
        logging.info("SMILES ready: %d/%d", ok, total)

    miner = DdiRuleMiner()
    if args.high_threshold is not None:
        miner.classifier.high_threshold = args.high_threshold
    if args.medium_threshold is not None:
        miner.classifier.medium_threshold = args.medium_threshold
    mined = miner.mine(
        max_drugs=max_drugs,
        max_pairs=max_pairs,
        batch_size=args.batch_size,
        allow_network=args.allow_network,
        inn_map_path=args.inn_map,
        formulary_path=args.formulary,
        exclusions_path=args.exclusions,
    )

    mined_path = resolve_path(args.mined_only)
    save_json(
        {
            "meta": mined["meta"],
            "interaction_rules": mined["interaction_rules"],
        },
        mined_path,
    )
    write_jsonl(mined["scores"], resolve_path(args.scores_jsonl))

    dup_rules = mine_duplicate_rules(inn_map_path=args.inn_map)
    aliases = build_alias_map_from_inn(args.inn_map)

    merged = merge_knowledge_base(
        manual_kb_path=args.manual_kb,
        mined_interaction_rules=mined["interaction_rules"],
        mined_duplicate_rules=dup_rules,
        mined_aliases=aliases,
        meta=mined["meta"],
    )
    merged["meta"]["duplicate_rules_mined"] = len(dup_rules)
    merged["meta"]["alias_entries"] = len(aliases)

    output_path = resolve_path(args.output)
    save_json(merged, output_path)

    print("=" * 60)
    print("DDI RULE MINING COMPLETE")
    print("=" * 60)
    print(f"  Pairs scored:     {mined['meta']['pairs_scored']}")
    print(f"  DDI rules mined:  {mined['meta']['rules_mined']}")
    print(f"    high:           {mined['meta']['high_risk_rules']}")
    print(f"    medium:         {mined['meta']['medium_risk_rules']}")
    print(f"  Duplicate rules:  {len(dup_rules)}")
    print(f"  Merged DDI total: {merged['meta']['total_interaction_rules']}")
    print(f"  Mined only:       {mined_path}")
    print(f"  Expanded KB:      {output_path}")

    if args.update_config:
        import yaml

        cfg_path = PROJECT_ROOT / "config.yaml"
        with cfg_path.open(encoding="utf-8") as handle:
            cfg = yaml.safe_load(handle) or {}
        rel = str(output_path.relative_to(PROJECT_ROOT))
        cfg.setdefault("data", {})["knowledge_base"] = rel
        with cfg_path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(cfg, handle, allow_unicode=True, sort_keys=False)
        print(f"  Updated config:   data.knowledge_base -> {rel}")

    sys.exit(0)


if __name__ == "__main__":
    main()
