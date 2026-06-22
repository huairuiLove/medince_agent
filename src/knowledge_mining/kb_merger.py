"""Merge manual + mined knowledge into a single safety rules JSON."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.knowledge_base import DEFAULT_KB_PATH, SafetyKnowledgeBase
from src.utils import normalize_text


def _pair_key(drugs: list[str]) -> tuple[str, str]:
    a, b = sorted(normalize_text(d) for d in drugs[:2])
    return a, b


def _manual_rule_pairs(kb: SafetyKnowledgeBase) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for rule in kb.get_interaction_rules():
        drugs = rule.get("drugs", [])
        if len(drugs) >= 2:
            pairs.add(_pair_key(drugs))
    return pairs


def _merge_aliases(
    manual: dict[str, list[str]],
    mined: dict[str, list[str]],
) -> dict[str, list[str]]:
    merged: dict[str, set[str]] = {}
    for source in (manual, mined):
        for canonical, aliases in source.items():
            canon = normalize_text(canonical)
            if not canon:
                continue
            bucket = merged.setdefault(canon, set())
            bucket.add(canon)
            for alias in aliases:
                alias_key = normalize_text(alias)
                if alias_key:
                    bucket.add(alias_key)
    return {key: sorted(values) for key, values in sorted(merged.items())}


def merge_knowledge_base(
    manual_kb_path: str | Path = DEFAULT_KB_PATH,
    mined_interaction_rules: list[dict[str, Any]] | None = None,
    mined_duplicate_rules: list[dict[str, Any]] | None = None,
    mined_aliases: dict[str, list[str]] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Combine curated minimal rules with model-mined extensions."""
    from pathlib import Path

    manual = SafetyKnowledgeBase(manual_kb_path)
    manual_pairs = _manual_rule_pairs(manual)

    interaction_rules: list[dict[str, Any]] = list(manual.get_interaction_rules())
    seen_pairs = set(manual_pairs)
    seen_rule_ids = {rule["rule_id"] for rule in interaction_rules}

    for rule in mined_interaction_rules or []:
        pair = _pair_key(rule.get("drugs", []))
        if not all(pair) or pair in seen_pairs:
            continue
        rule_id = rule.get("rule_id", "")
        if rule_id in seen_rule_ids:
            continue
        interaction_rules.append(rule)
        seen_pairs.add(pair)
        seen_rule_ids.add(rule_id)

    duplicate_rules = list(manual.get_duplicate_rules())
    seen_dup = {normalize_text(rule.get("ingredient", "")) for rule in duplicate_rules}
    for rule in mined_duplicate_rules or []:
        ingredient = normalize_text(rule.get("ingredient", ""))
        if not ingredient or ingredient in seen_dup:
            continue
        duplicate_rules.append(rule)
        seen_dup.add(ingredient)

    merged_meta = {
        "version": "expanded_mined_v1",
        "merged_at": datetime.now(timezone.utc).isoformat(),
        "manual_rule_count": len(manual.get_interaction_rules()),
        "mined_interaction_count": len(interaction_rules) - len(manual.get_interaction_rules()),
        "total_interaction_rules": len(interaction_rules),
    }
    if meta:
        merged_meta.update(meta)

    return {
        "meta": merged_meta,
        "drug_aliases": _merge_aliases(
            manual.data.get("drug_aliases", {}),
            mined_aliases or {},
        ),
        "interaction_rules": interaction_rules,
        "duplicate_ingredient_rules": duplicate_rules,
        "population_rules": list(manual.get_population_rules()),
        "allergy_rules": list(manual.get_allergy_rules()),
    }
