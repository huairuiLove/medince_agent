from __future__ import annotations

from pathlib import Path
from typing import Any

from src.utils import load_json, normalize_text


DEFAULT_KB_PATH = (
    Path(__file__).resolve().parent.parent / "datasets" / "knowledge" / "minimal_drug_safety_rules.json"
)


def get_default_kb_path() -> Path:
    """Resolve knowledge base path from config."""
    from src.config import get_config, resolve_path

    rel = get_config().get("data", {}).get("knowledge_base")
    if not rel:
        raise FileNotFoundError("config data.knowledge_base is not set")
    path = resolve_path(rel)
    if not path.exists():
        raise FileNotFoundError(f"Knowledge base not found: {path}")
    return path


def summarize_kb_stats(data: dict[str, Any]) -> dict[str, Any]:
    aliases = data.get("drug_aliases") or {}
    interaction = data.get("interaction_rules") or []
    return {
        "interaction_rules": len(interaction),
        "duplicate_ingredient_rules": len(data.get("duplicate_ingredient_rules") or []),
        "population_rules": len(data.get("population_rules") or []),
        "allergy_rules": len(data.get("allergy_rules") or []),
        "scenario_rules": len(data.get("scenario_rules") or []),
        "drug_aliases": len(aliases) if isinstance(aliases, dict) else 0,
        "total_rules": (
            len(interaction)
            + len(data.get("duplicate_ingredient_rules") or [])
            + len(data.get("population_rules") or [])
            + len(data.get("allergy_rules") or [])
            + len(data.get("scenario_rules") or [])
        ),
    }


def load_kb_stats(kb_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(kb_path) if kb_path else get_default_kb_path()
    from src.config import get_config

    version = get_config().get("clinical_knowledge", {}).get("version", path.stem)
    stats = summarize_kb_stats(load_json(path))
    stats["version"] = version
    stats["path"] = path.name
    return stats


class SafetyKnowledgeBase:
    def __init__(self, kb_path: str | Path | None = None) -> None:
        self.kb_path = Path(kb_path) if kb_path else get_default_kb_path()
        self.data = load_json(self.kb_path)
        self.alias_to_canonical = self._build_alias_map()

    def _build_alias_map(self) -> dict[str, str]:
        alias_map: dict[str, str] = {}

        for canonical, aliases in self.data.get("drug_aliases", {}).items():
            normalized_canonical = normalize_text(canonical)
            alias_map[normalized_canonical] = normalized_canonical
            for alias in aliases:
                alias_map[normalize_text(alias)] = normalized_canonical

        for rule in self.data.get("duplicate_ingredient_rules", []):
            ingredient = normalize_text(rule["ingredient"])
            alias_map[ingredient] = ingredient
            for alias in rule.get("aliases", []):
                alias_map[normalize_text(alias)] = ingredient

        from src.config import datasets_path

        inn_path = datasets_path("knowledge/drug_inn_map.json")
        if inn_path.exists():
            inn_data = load_json(inn_path)
            for cn, en in (inn_data.get("map") or {}).items():
                canonical = normalize_text(str(en))
                if not canonical:
                    continue
                alias_map[normalize_text(str(cn))] = canonical
                alias_map[canonical] = canonical

        return alias_map

    def resolve_drug(self, name: str, hospital_drug_id: str | None = None) -> str:
        normalized = normalize_text(name)
        if not normalized:
            return ""
        if normalized in self.alias_to_canonical:
            return self.alias_to_canonical[normalized]

        for alias, canonical in sorted(self.alias_to_canonical.items(), key=lambda item: len(item[0]), reverse=True):
            if alias and alias in normalized:
                return canonical
        return normalized

    def get_interaction_rules(self) -> list[dict[str, Any]]:
        return list(self.data.get("interaction_rules", []))

    def get_duplicate_rules(self) -> list[dict[str, Any]]:
        return list(self.data.get("duplicate_ingredient_rules", []))

    def get_population_rules(self) -> list[dict[str, Any]]:
        return list(self.data.get("population_rules", []))

    def get_allergy_rules(self) -> list[dict[str, Any]]:
        return list(self.data.get("allergy_rules", []))

    def get_scenario_rules(self) -> list[dict[str, Any]]:
        return list(self.data.get("scenario_rules", []))

    def interaction_rules_for_pair(
        self,
        drug_a: str,
        drug_b: str,
        department: str | None = None,
    ) -> list[dict[str, Any]]:
        """Lookup interaction rules by canonical pair (O(1) index).

        When department is provided, rules are sorted by department relevance
        (same-dept first) but never filtered out.
        """
        if not hasattr(self, "_interaction_pair_index"):
            index: dict[tuple[str, str], list[dict[str, Any]]] = {}
            for rule in self.get_interaction_rules():
                drugs = rule.get("drugs", [])
                if len(drugs) < 2:
                    continue
                pair = tuple(sorted(self.resolve_drug(d) for d in drugs[:2]))
                if not all(pair):
                    continue
                index.setdefault(pair, []).append(rule)
            self._interaction_pair_index = index
        key = tuple(sorted([self.resolve_drug(drug_a), self.resolve_drug(drug_b)]))
        rules = list(self._interaction_pair_index.get(key, []))
        if not department or not rules:
            return rules

        dept_id = department.strip().lower()

        def _sort_key(rule: dict[str, Any]) -> tuple[int, int]:
            rule_dept = str(rule.get("department") or "").strip().lower()
            if rule_dept == dept_id:
                return (0, 0)
            if not rule_dept:
                return (1, 0)
            return (2, 0)

        return sorted(rules, key=_sort_key)

    def rule_lookup(self) -> dict[str, dict[str, Any]]:
        """Build rule_id → rule dict for prioritizer annotations."""
        if not hasattr(self, "_rule_lookup_cache"):
            lookup: dict[str, dict[str, Any]] = {}
            for rule in self.get_interaction_rules():
                rid = rule.get("rule_id")
                if rid:
                    lookup[str(rid)] = rule
            for rule in self.get_population_rules():
                rid = rule.get("rule_id")
                if rid:
                    lookup[str(rid)] = rule
            for rule in self.get_allergy_rules():
                rid = rule.get("rule_id")
                if rid:
                    lookup[str(rid)] = rule
            for rule in self.get_scenario_rules():
                rid = rule.get("rule_id")
                if rid:
                    lookup[str(rid)] = rule
            for rule in self.get_duplicate_rules():
                rid = rule.get("rule_id")
                if rid:
                    lookup[str(rid)] = rule
            self._rule_lookup_cache = lookup
        return self._rule_lookup_cache
