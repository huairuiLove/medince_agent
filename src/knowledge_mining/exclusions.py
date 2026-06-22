"""DDI mining exclusions — curated false-positive pairs and skip lists."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.config import resolve_path
from src.utils import load_json, normalize_text

DEFAULT_EXCLUSIONS_PATH = "data/knowledge/ddi_mining_exclusions.json"


def _pair_tuple(drug_a: str, drug_b: str) -> tuple[str, str]:
    return tuple(sorted([normalize_text(drug_a), normalize_text(drug_b)]))


def load_mining_exclusions(path: str | Path | None = None) -> dict[str, Any]:
    file_path = resolve_path(path or DEFAULT_EXCLUSIONS_PATH)
    if not file_path.exists():
        return {"excluded_pairs": [], "excluded_drugs": []}
    data = load_json(file_path)
    return {
        "excluded_pairs": data.get("excluded_pairs", []),
        "excluded_drugs": data.get("excluded_drugs", []),
        "meta": data.get("meta", {}),
    }


def build_exclusion_index(path: str | Path | None = None) -> tuple[set[tuple[str, str]], set[str]]:
    data = load_mining_exclusions(path)
    pairs: set[tuple[str, str]] = set()
    for item in data.get("excluded_pairs", []):
        if isinstance(item, list) and len(item) >= 2:
            key = _pair_tuple(item[0], item[1])
            if all(key):
                pairs.add(key)
        elif isinstance(item, dict):
            key = _pair_tuple(item.get("drug_a", ""), item.get("drug_b", ""))
            if all(key):
                pairs.add(key)

    drugs = {normalize_text(d) for d in data.get("excluded_drugs", []) if normalize_text(d)}
    return pairs, drugs


def is_pair_excluded(
    drug_a: str,
    drug_b: str,
    excluded_pairs: set[tuple[str, str]],
) -> bool:
    return _pair_tuple(drug_a, drug_b) in excluded_pairs
