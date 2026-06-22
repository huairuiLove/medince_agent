from __future__ import annotations

from src.agents.base import LLMAgent
from src.drug_catalog.catalog_service import get_drug_catalog_service
from src.llm.client import LLMClient
from src.prompts import PHARMACY_SYSTEM_PROMPT
from src.schemas import AgentOpinion, CandidateDrug, PatientContext, RuleEvidence


class PharmacyInventoryAgent(LLMAgent):
    agent_id = "pharmacy_inventory"
    agent_name = "药房库管"
    role = "库存、院内可开品种与替代方案"
    system_prompt = PHARMACY_SYSTEM_PROMPT

    def __init__(self, llm: LLMClient, system_prompt: str | None = None) -> None:
        super().__init__(llm, system_prompt=system_prompt)
        self.catalog = get_drug_catalog_service()

    def review(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        rule_evidence: list[RuleEvidence],
    ) -> AgentOpinion:
        opinion = super().review(patient_context, candidate_drugs, rule_evidence)
        stock_issues: list[str] = []
        formulary_issues: list[str] = []
        alternatives: list[str] = list(opinion.alternatives)

        if not self.catalog.is_loaded():
            return opinion

        for drug in candidate_drugs:
            record = None
            if drug.hospital_drug_id:
                record = self.catalog.get_by_id(drug.hospital_drug_id)
            if record is None:
                record = self.catalog.resolve_by_name(drug.name or drug.ingredient)
            if record is None:
                continue

            if not record.in_formulary:
                formulary_issues.append(f"{record.display_name} 不在院基本目录")
            if not record.in_stock:
                stock_issues.append(f"{record.display_name} 当前缺货")
                for alt in self.catalog.list_alternatives(record.hospital_drug_id):
                    alternatives.append(alt.display_name)

        if formulary_issues or stock_issues:
            opinion.reasons = formulary_issues + stock_issues + opinion.reasons
            opinion.alternatives = alternatives
            if formulary_issues:
                opinion.risk_level = "medium"
            elif stock_issues:
                opinion.risk_level = "low"
            opinion.summary = "部分候选药物需核对院目录/库存并更换为可调配品种。"
        return opinion
