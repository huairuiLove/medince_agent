from __future__ import annotations

from pathlib import Path
from typing import Any

from src.utils import load_json, normalize_text


DEFAULT_KB_PATH = Path(__file__).resolve().parent.parent / "data" / "knowledge" / "minimal_drug_safety_rules.json"


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

    def interaction_rules_for_pair(self, drug_a: str, drug_b: str) -> list[dict[str, Any]]:
        """Lookup interaction rules by canonical pair (O(1) index)."""
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
        return list(self._interaction_pair_index.get(key, []))
