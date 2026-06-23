"""Mine DDI interaction rules with Bio_ClinicalBERT."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.knowledge_mining.drug_universe import collect_canonical_drugs, iter_drug_pairs
from src.knowledge_mining.exclusions import build_exclusion_index, is_pair_excluded
from src.safety_models.ddi_classifier import DdiClassifier
from src.safety_models.smiles_lookup import SmilesLookup
from src.utils import normalize_text

logger = logging.getLogger(__name__)


def _rule_id(drug_a: str, drug_b: str) -> str:
    pair = sorted([normalize_text(drug_a), normalize_text(drug_b)])
    return f"mined_ddi_{pair[0]}_{pair[1]}"


def _interaction_rule_from_score(score: dict[str, Any]) -> dict[str, Any]:
    drug_a = score["drug_a"]
    drug_b = score["drug_b"]
    prob = float(score["positive_prob"])
    risk = score["risk_level"]
    return {
        "rule_id": _rule_id(drug_a, drug_b),
        "drugs": sorted([drug_a, drug_b], key=normalize_text),
        "risk_level": risk,
        "summary": (
            f"DDI 模型预测 {drug_a} 与 {drug_b} 存在药物相互作用"
            f"（概率 {prob:.0%}）。"
        ),
        "mechanism": "Bio_ClinicalBERT SMILES 药对分类（规则挖掘）",
        "recommendation": "建议人工复核并查阅说明书；挖掘规则需临床确认后纳入常规审查。",
        "alternatives": ["优先查阅药品说明书或咨询临床药师。"],
        "clarification_fields": ["current_medications"],
        "source": "ddi_bert_mined",
        "positive_prob": round(prob, 4),
        "mined_at": datetime.now(timezone.utc).isoformat(),
    }


class DdiRuleMiner:
    def __init__(
        self,
        classifier: DdiClassifier | None = None,
        smiles_lookup: SmilesLookup | None = None,
    ) -> None:
        self.classifier = classifier or get_ddi_classifier().require_ready()
        self.smiles = smiles_lookup or self.classifier.smiles

    def filter_drugs_with_smiles(
        self,
        drugs: list[str],
        *,
        allow_network: bool = False,
    ) -> list[str]:
        ready: list[str] = []
        for drug in drugs:
            if self.smiles.resolve(drug, allow_network=allow_network):
                ready.append(drug)
        return ready

    def mine(
        self,
        *,
        max_drugs: int | None = None,
        max_pairs: int | None = None,
        batch_size: int = 32,
        allow_network: bool = False,
        inn_map_path: str | None = None,
        formulary_path: str | None = None,
        exclusions_path: str | None = None,
    ) -> dict[str, Any]:
        self.classifier.require_ready()
        universe = collect_canonical_drugs(
            inn_map_path=inn_map_path or "datasets/knowledge/drug_inn_map.json",
            formulary_path=formulary_path or "datasets/hospital/formulary_demo.csv",
            max_drugs=max_drugs,
        )
        drugs = self.filter_drugs_with_smiles(universe, allow_network=allow_network)
        excluded_pairs, excluded_drugs = build_exclusion_index(exclusions_path)
        if excluded_drugs:
            drugs = [d for d in drugs if normalize_text(d) not in excluded_drugs]

        raw_pairs = iter_drug_pairs(drugs)
        pairs: list[tuple[str, str]] = []
        skipped_excluded = 0
        for drug_a, drug_b in raw_pairs:
            if is_pair_excluded(drug_a, drug_b, excluded_pairs):
                skipped_excluded += 1
                continue
            pairs.append((drug_a, drug_b))
        if max_pairs is not None and max_pairs > 0:
            pairs = pairs[:max_pairs]

        logger.info(
            "Scoring %d pairs across %d drugs (universe=%d, excluded_pairs=%d)",
            len(pairs),
            len(drugs),
            len(universe),
            skipped_excluded,
        )

        scores = self.classifier.predict_pairs(pairs, batch_size=batch_size)
        rules = [_interaction_rule_from_score(score) for score in scores]

        high = sum(1 for rule in rules if rule["risk_level"] == "high")
        medium = sum(1 for rule in rules if rule["risk_level"] == "medium")

        return {
            "meta": {
                "mined_at": datetime.now(timezone.utc).isoformat(),
                "model": "ddi_bert",
                "universe_size": len(universe),
                "drugs_with_smiles": len(drugs),
                "pairs_scored": len(pairs),
                "rules_mined": len(rules),
                "high_risk_rules": high,
                "medium_risk_rules": medium,
                "high_threshold": self.classifier.high_threshold,
                "medium_threshold": self.classifier.medium_threshold,
                "excluded_pair_skips": skipped_excluded,
                "excluded_drug_count": len(excluded_drugs),
            },
            "interaction_rules": rules,
            "scores": scores,
        }
