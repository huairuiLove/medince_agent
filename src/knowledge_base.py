from __future__ import annotations

from pathlib import Path
from typing import Any

from src.utils import load_json, normalize_text


DEFAULT_KB_PATH = Path(__file__).resolve().parent.parent / "data" / "knowledge" / "minimal_drug_safety_rules.json"


class SafetyKnowledgeBase:
    def __init__(self, kb_path: str | Path = DEFAULT_KB_PATH) -> None:
        self.kb_path = Path(kb_path)
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
