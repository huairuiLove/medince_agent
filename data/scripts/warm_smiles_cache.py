#!/usr/bin/env python3
"""Pre-fetch PubChem SMILES for formulary / rule-base drugs into local cache."""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_config
from src.knowledge_base import DEFAULT_KB_PATH, SafetyKnowledgeBase
from src.safety_models.smiles_cache import SmilesCache
from src.safety_models.smiles_lookup import SmilesLookup, DEFAULT_INN_MAP_PATH
from src.utils import load_json, normalize_text, save_json


def collect_drug_names(formulary_path: Path, kb_path: Path) -> tuple[set[str], dict[str, str]]:
    names: set[str] = set()
    cn_to_en: dict[str, str] = {}

    kb = SafetyKnowledgeBase(kb_path)
    for canonical, aliases in kb.data.get("drug_aliases", {}).items():
        names.add(normalize_text(canonical))
        for alias in aliases:
            alias_key = normalize_text(alias)
            if alias_key and not alias_key.isascii():
                cn_to_en[alias_key] = normalize_text(canonical)
    for rule in kb.get_interaction_rules():
        for drug in rule.get("drugs", []):
            names.add(kb.resolve_drug(drug))
    for rule in kb.get_duplicate_rules():
        names.add(kb.resolve_drug(rule["ingredient"]))
    for rule in kb.get_population_rules():
        for drug in rule.get("trigger_drugs", []):
            names.add(kb.resolve_drug(drug))
    for rule in kb.get_allergy_rules():
        for drug in rule.get("trigger_drugs", []):
            names.add(kb.resolve_drug(drug))

    if formulary_path.exists():
        with formulary_path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                en = normalize_text(row.get("generic_name_en", ""))
                cn = normalize_text(row.get("generic_name_cn", ""))
                if en:
                    names.add(en)
                if cn and en:
                    cn_to_en[cn] = en

    return names, cn_to_en


def main() -> None:
    parser = argparse.ArgumentParser(description="Warm SMILES cache via PubChem")
    parser.add_argument(
        "--formulary",
        default="datasets/hospital/formulary_demo.csv",
        help="Hospital formulary CSV",
    )
    parser.add_argument("--dry-run", action="store_true", help="List names only")
    args = parser.parse_args()

    load_config()
    formulary_path = PROJECT_ROOT / args.formulary
    names, cn_to_en = collect_drug_names(formulary_path, DEFAULT_KB_PATH)

    inn_map_path = DEFAULT_INN_MAP_PATH
    save_json({"map": cn_to_en}, inn_map_path)
    print(f"Wrote INN map ({len(cn_to_en)} entries) -> {inn_map_path}")

    if args.dry_run:
        for name in sorted(names):
            print(name)
        print(f"Total: {len(names)}")
        return

    lookup = SmilesLookup(inn_map_path=inn_map_path)
    cache = SmilesCache()
    resolved = 0
    skipped = 0
    failed = 0

    for name in sorted(names):
        if not name:
            continue
        if lookup.resolve(name, allow_network=False):
            skipped += 1
            continue
        smiles = lookup.resolve(name, allow_network=True)
        if smiles:
            resolved += 1
            print(f"  [OK] {name}")
        else:
            failed += 1
            print(f"  [MISS] {name}")

    print(f"\nDone. newly_fetched={resolved}, already_cached={skipped}, failed={failed}, cache_size={cache.count()}")


if __name__ == "__main__":
    main()
