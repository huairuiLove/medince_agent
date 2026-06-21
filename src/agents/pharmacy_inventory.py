from __future__ import annotations

from pathlib import Path

from src.agents.base import LLMAgent
from src.llm.client import LLMClient
from src.prompts import PHARMACY_SYSTEM_PROMPT
from src.schemas import AgentOpinion, CandidateDrug, PatientContext, RuleEvidence
from src.utils import load_json, normalize_text


FORMULARY_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "knowledge" / "pharmacy_formulary.json"


class PharmacyInventoryAgent(LLMAgent):
    agent_id = "pharmacy_inventory"
    agent_name = "药房库管"
    role = "库存、院内可开品种与替代方案"
    system_prompt = PHARMACY_SYSTEM_PROMPT

    def __init__(self, llm: LLMClient) -> None:
        super().__init__(llm)
        self.formulary = load_json(FORMULARY_PATH).get("formulary", {})

    def review(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        rule_evidence: list[RuleEvidence],
    ) -> AgentOpinion:
        opinion = super().review(patient_context, candidate_drugs, rule_evidence)
        stock_issues: list[str] = []
        alternatives: list[str] = list(opinion.alternatives)
        for drug in candidate_drugs:
            canonical = normalize_text(drug.ingredient or drug.name)
            entry = self.formulary.get(canonical.replace(" ", ""))
            if entry is None:
                for key, value in self.formulary.items():
                    if key in canonical or canonical in key:
                        entry = value
                        break
            if entry and not entry.get("in_stock", True):
                stock_issues.append(f"{drug.name} 当前缺货")
                alternatives.extend(entry.get("alternatives", []))
        if stock_issues:
            opinion.reasons = stock_issues + opinion.reasons
            opinion.alternatives = alternatives
            opinion.risk_level = "low"
            opinion.summary = "部分候选药物需更换为院内可调配品种。"
        return opinion
