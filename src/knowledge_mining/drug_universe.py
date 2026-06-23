"""Drug universe collection for knowledge mining."""

from __future__ import annotations

import csv
from pathlib import Path

from src.config import resolve_path
from src.utils import load_json, normalize_text

DEFAULT_INN_MAP = "datasets/knowledge/drug_inn_map.json"
DEFAULT_FORMULARY = "datasets/hospital/formulary_demo.csv"


def _primary_canonical(english_name: str) -> str:
    """Normalize formulary / INN English name to canonical key."""
    return normalize_text(english_name)


def collect_canonical_drugs(
    *,
    inn_map_path: str | Path = DEFAULT_INN_MAP,
    formulary_path: str | Path = DEFAULT_FORMULARY,
    max_drugs: int | None = None,
) -> list[str]:
    """Unique canonical drug names from INN map + hospital formulary."""
    names: set[str] = set()

    inn_file = resolve_path(inn_map_path)
    if inn_file.exists():
        data = load_json(inn_file)
        for english in data.get("map", {}).values():
            canonical = _primary_canonical(english)
            if canonical:
                names.add(canonical)

    formulary_file = resolve_path(formulary_path)
    if formulary_file.exists():
        with formulary_file.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                english = normalize_text(row.get("generic_name_en", ""))
                if english:
                    names.add(english)

    ordered = sorted(names)
    if max_drugs is not None and max_drugs > 0:
        return ordered[:max_drugs]
    return ordered


def build_alias_map_from_inn(inn_map_path: str | Path = DEFAULT_INN_MAP) -> dict[str, list[str]]:
    """Group Chinese trade/generic names under English canonical keys."""
    inn_file = resolve_path(inn_map_path)
    if not inn_file.exists():
        return {}

    grouped: dict[str, set[str]] = {}
    for chinese, english in load_json(inn_file).get("map", {}).items():
        canonical = _primary_canonical(english)
        cn = normalize_text(chinese)
        if not canonical:
            continue
        bucket = grouped.setdefault(canonical, set())
        bucket.add(canonical)
        if cn:
            bucket.add(cn)

    return {key: sorted(values) for key, values in sorted(grouped.items())}


def iter_drug_pairs(drugs: list[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for i, drug_a in enumerate(drugs):
        for drug_b in drugs[i + 1:]:
            pairs.append((drug_a, drug_b))
    return pairs
