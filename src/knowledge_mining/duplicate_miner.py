"""Mine duplicate-ingredient rules from INN / formulary groupings."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.knowledge_mining.drug_universe import build_alias_map_from_inn
from src.utils import normalize_text


def mine_duplicate_rules(
    *,
    inn_map_path: str = "data/knowledge/drug_inn_map.json",
    min_aliases: int = 2,
) -> list[dict[str, Any]]:
    """Create duplicate-ingredient rules when multiple CN names map to same INN."""
    alias_map = build_alias_map_from_inn(inn_map_path)
    rules: list[dict[str, Any]] = []
    mined_at = datetime.now(timezone.utc).isoformat()

    for canonical, aliases in alias_map.items():
        if len(aliases) < min_aliases:
            continue
        ingredient = normalize_text(canonical)
        if not ingredient:
            continue
        rules.append(
            {
                "rule_id": f"mined_dup_{ingredient.replace(' ', '_')}",
                "ingredient": ingredient,
                "aliases": aliases,
                "risk_level": "medium",
                "summary": f"重复使用含 {ingredient} 成分的药物可能导致剂量叠加。",
                "mechanism": "相同活性成分重复（INN 映射挖掘）",
                "recommendation": "避免重复开具同一活性成分的不同制剂。",
                "alternatives": ["统一为单一制剂并核对总日剂量。"],
                "clarification_fields": ["current_medications"],
                "source": "inn_map_mined",
                "mined_at": mined_at,
            }
        )
    return rules
