"""Merge manual + mined + curated + external knowledge into a single safety rules JSON."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
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
    *extra: dict[str, list[str]] | None,
) -> dict[str, list[str]]:
    merged: dict[str, set[str]] = {}
    for source in (manual, *extra):
        if not source:
            continue
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


def _append_interaction_rules(
    target: list[dict[str, Any]],
    incoming: list[dict[str, Any]] | None,
    seen_pairs: set[tuple[str, str]],
    seen_rule_ids: set[str],
) -> int:
    added = 0
    for rule in incoming or []:
        pair = _pair_key(rule.get("drugs", []))
        if not all(pair) or pair in seen_pairs:
            continue
        rule_id = rule.get("rule_id", "")
        if rule_id in seen_rule_ids:
            continue
        target.append(rule)
        seen_pairs.add(pair)
        seen_rule_ids.add(rule_id)
        added += 1
    return added


def _merge_rule_list_by_id(
    base: list[dict[str, Any]],
    incoming: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], int]:
    merged = list(base)
    seen_ids = {rule.get("rule_id", "") for rule in merged}
    added = 0
    for rule in incoming or []:
        rule_id = rule.get("rule_id", "")
        if not rule_id or rule_id in seen_ids:
            continue
        merged.append(rule)
        seen_ids.add(rule_id)
        added += 1
    return merged, added


def merge_knowledge_base(
    manual_kb_path: str | Path = DEFAULT_KB_PATH,
    mined_interaction_rules: list[dict[str, Any]] | None = None,
    mined_duplicate_rules: list[dict[str, Any]] | None = None,
    mined_aliases: dict[str, list[str]] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Combine curated minimal rules with model-mined extensions."""
    manual = SafetyKnowledgeBase(manual_kb_path)
    manual_pairs = _manual_rule_pairs(manual)

    interaction_rules: list[dict[str, Any]] = list(manual.get_interaction_rules())
    seen_pairs = set(manual_pairs)
    seen_rule_ids = {rule["rule_id"] for rule in interaction_rules}

    mined_added = _append_interaction_rules(
        interaction_rules,
        mined_interaction_rules,
        seen_pairs,
        seen_rule_ids,
    )

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
        "mined_interaction_count": mined_added,
        "total_interaction_rules": len(interaction_rules),
    }
    if meta:
        merged_meta.update(meta)

    return {
        "meta": merged_meta,
        "drug_aliases": _merge_aliases(manual.data.get("drug_aliases", {}), mined_aliases),
        "interaction_rules": interaction_rules,
        "duplicate_ingredient_rules": duplicate_rules,
        "population_rules": list(manual.get_population_rules()),
        "allergy_rules": list(manual.get_allergy_rules()),
    }


def merge_all_sources(
    *,
    manual_kb_path: str | Path = DEFAULT_KB_PATH,
    expanded_kb: dict[str, Any] | None = None,
    curated: dict[str, Any] | None = None,
    twosides: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge minimal, expanded mined, curated, and TWOSIDES rule sources."""
    manual = SafetyKnowledgeBase(manual_kb_path)
    if expanded_kb is None:
        raise ValueError("expanded_kb is required")
    base = expanded_kb

    interaction_rules: list[dict[str, Any]] = list(base.get("interaction_rules", []))
    seen_pairs = {_pair_key(rule.get("drugs", [])) for rule in interaction_rules if len(rule.get("drugs", [])) >= 2}
    seen_rule_ids = {rule.get("rule_id", "") for rule in interaction_rules}

    curated_added = _append_interaction_rules(
        interaction_rules,
        (curated or {}).get("interaction_rules"),
        seen_pairs,
        seen_rule_ids,
    )

    twosides_added = 0
    twosides_upgraded = 0
    pair_index = {_pair_key(rule.get("drugs", [])): rule for rule in interaction_rules if len(rule.get("drugs", [])) >= 2}
    for signal in (twosides or {}).get("signals", []):
        drugs = signal.get("drugs", [])
        if len(drugs) < 2:
            continue
        pair = _pair_key(drugs)
        if not all(pair):
            continue
        existing = pair_index.get(pair)
        if existing:
            event_name = signal.get("event_name", "")
            if event_name and event_name not in existing.get("mechanism", ""):
                existing["mechanism"] = (
                    f"{existing.get('mechanism', '').rstrip('。')}；TWOSIDES 报告：{event_name}。"
                )
            if signal.get("evidence_level") == "A":
                existing["evidence_level"] = "A"
            twosides_upgraded += 1
            continue
        rule_id = signal.get("rule_id", "")
        if rule_id in seen_rule_ids or pair in seen_pairs:
            continue
        interaction_rules.append(signal)
        pair_index[pair] = signal
        seen_pairs.add(pair)
        seen_rule_ids.add(rule_id)
        twosides_added += 1

    population_rules, pop_added = _merge_rule_list_by_id(
        list(base.get("population_rules", manual.get_population_rules())),
        (curated or {}).get("population_rules"),
    )
    allergy_rules, allergy_added = _merge_rule_list_by_id(
        list(base.get("allergy_rules", manual.get_allergy_rules())),
        (curated or {}).get("allergy_rules"),
    )
    scenario_rules, scenario_added = _merge_rule_list_by_id(
        list(base.get("scenario_rules", [])),
        (curated or {}).get("scenario_rules"),
    )

    duplicate_rules = list(base.get("duplicate_ingredient_rules", manual.get_duplicate_rules()))

    merged_meta: dict[str, Any] = {
        "version": "hospital_production_v4",
        "merged_at": datetime.now(timezone.utc).isoformat(),
        "manual_interaction_count": len(manual.get_interaction_rules()),
        "expanded_interaction_count": len(base.get("interaction_rules", [])),
        "curated_interaction_added": curated_added,
        "twosides_interaction_added": twosides_added,
        "twosides_pairs_upgraded": twosides_upgraded,
        "total_interaction_rules": len(interaction_rules),
        "population_rules": len(population_rules),
        "population_rules_added": pop_added,
        "allergy_rules": len(allergy_rules),
        "allergy_rules_added": allergy_added,
        "scenario_rules": len(scenario_rules),
        "scenario_rules_added": scenario_added,
        "duplicate_rules": len(duplicate_rules),
    }
    if meta:
        merged_meta.update(meta)
    if twosides and twosides.get("meta"):
        merged_meta["twosides_meta"] = twosides["meta"]
    if curated and curated.get("meta"):
        merged_meta["curated_meta"] = curated["meta"]

    return {
        "meta": merged_meta,
        "drug_aliases": _merge_aliases(
            base.get("drug_aliases", {}),
            manual.data.get("drug_aliases", {}),
            (curated or {}).get("drug_aliases"),
        ),
        "interaction_rules": interaction_rules,
        "duplicate_ingredient_rules": duplicate_rules,
        "population_rules": population_rules,
        "allergy_rules": allergy_rules,
        "scenario_rules": scenario_rules,
    }
