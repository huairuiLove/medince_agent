from __future__ import annotations

import logging
from pathlib import Path

from src.config import datasets_path, get_config, resolve_path
from src.safety_models.pubchem_client import PubChemClient
from src.safety_models.smiles_cache import SmilesCache
from src.utils import load_json, normalize_text

logger = logging.getLogger(__name__)

DEFAULT_SMILES_PATH = datasets_path("knowledge/drug_smiles.json")
DEFAULT_INN_MAP_PATH = datasets_path("knowledge/drug_inn_map.json")


class SmilesLookup:
    """Resolve canonical drug name → SMILES: static JSON → SQLite cache → PubChem."""

    def __init__(
        self,
        smiles_path: str | Path | None = None,
        inn_map_path: str | Path | None = None,
        cache: SmilesCache | None = None,
        pubchem: PubChemClient | None = None,
    ) -> None:
        cfg = get_config().get("safety_models", {})
        pubchem_cfg = cfg.get("pubchem", {})

        smiles_file = resolve_path(smiles_path or cfg.get("ddi_bert", {}).get("smiles_path", DEFAULT_SMILES_PATH))
        data = load_json(smiles_file)
        self._static: dict[str, str] = {
            normalize_text(name): value for name, value in data.get("smiles", {}).items()
        }

        inn_file = resolve_path(inn_map_path or pubchem_cfg.get("inn_map_path", DEFAULT_INN_MAP_PATH))
        inn_data = load_json(inn_file) if Path(inn_file).exists() else {}
        self._cn_to_en: dict[str, str] = {
            normalize_text(cn): normalize_text(en)
            for cn, en in inn_data.get("map", {}).items()
        }
        self._merge_rule_aliases()

        self._cache = cache or SmilesCache(pubchem_cfg.get("cache_path"))
        self._pubchem = pubchem or PubChemClient(
            enabled=bool(pubchem_cfg.get("enabled", True)),
            timeout=float(pubchem_cfg.get("timeout", 10)),
            rate_limit_seconds=float(pubchem_cfg.get("rate_limit_seconds", 0.25)),
        )

    def _merge_rule_aliases(self) -> None:
        from src.knowledge_base import DEFAULT_KB_PATH, SafetyKnowledgeBase

        kb = SafetyKnowledgeBase(DEFAULT_KB_PATH)
        for canonical, aliases in kb.data.get("drug_aliases", {}).items():
            canon = normalize_text(canonical)
            for alias in aliases:
                alias_key = normalize_text(alias)
                if alias_key and not alias_key.isascii():
                    self._cn_to_en.setdefault(alias_key, canon)

    def _inn_name(self, canonical_name: str) -> str:
        key = normalize_text(canonical_name)
        if not key:
            return ""
        if key in self._static or key.isascii():
            return key
        return self._cn_to_en.get(key, key)

    def resolve(self, canonical_name: str, *, allow_network: bool = True) -> str | None:
        key = normalize_text(canonical_name)
        if not key:
            return None

        if key in self._static:
            return self._static[key]

        cached = self._cache.get(key)
        if cached:
            return cached

        inn = self._inn_name(canonical_name)
        if inn and inn != key:
            if inn in self._static:
                return self._static[inn]
            cached = self._cache.get(inn)
            if cached:
                return cached

        if not allow_network or not self._pubchem.enabled:
            return None

        query = inn or key
        smiles = self._pubchem.fetch_smiles(query)
        if smiles:
            self._cache.put(key, smiles, pubchem_query=query, source="pubchem")
            if inn and inn != key:
                self._cache.put(inn, smiles, pubchem_query=query, source="pubchem")
            logger.debug("PubChem resolved %s -> SMILES", query)
        return smiles

    def status(self) -> dict:
        return {
            "static_entries": len(self._static),
            "inn_map_entries": len(self._cn_to_en),
            "cache": self._cache.stats(),
            "pubchem_enabled": self._pubchem.enabled,
        }
