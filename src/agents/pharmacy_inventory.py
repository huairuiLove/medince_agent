from __future__ import annotations

from src.agents.base import LLMAgent
from src.drug_catalog.catalog_service import DrugCatalogService, get_drug_catalog_service
from src.drug_catalog.models import HospitalDrug
from src.llm.client import LLMClient
from src.prompts import PHARMACY_SYSTEM_PROMPT
from src.schemas import AgentOpinion, CandidateDrug, PatientContext, RuleEvidence


class PharmacyInventoryAgent(LLMAgent):
    agent_id = "pharmacy_inventory"
    agent_name = "药房库管"
    role = "库存、院内可开品种与替代方案"
    system_prompt = PHARMACY_SYSTEM_PROMPT

    def __init__(
        self,
        llm: LLMClient,
        system_prompt: str | None = None,
        catalog: DrugCatalogService | None = None,
    ) -> None:
        super().__init__(llm, system_prompt=system_prompt)
        self.catalog = catalog if catalog is not None else get_drug_catalog_service()

    def build_user_input(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        rule_evidence: list[RuleEvidence],
    ) -> str:
        """Fallback LLM path — omit clinical rule_evidence to avoid role drift."""
        payload = {
            "patient_context": patient_context.model_dump(),
            "candidate_drugs": [d.model_dump() for d in candidate_drugs],
            "instruction": (
                "仅审查院目录与库存；不要引用 DDI/剂量/过敏规则；"
                "block_decision 仅因非目录或全院缺货且无院内替代时为 true。"
            ),
        }
        from src.prompts import pretty_json

        return pretty_json(payload)

    def review(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        rule_evidence: list[RuleEvidence],
    ) -> AgentOpinion:
        if self.catalog.is_loaded():
            return self._review_from_catalog(candidate_drugs, debate_round=1)
        return self._normalize_llm_opinion(
            super().review(patient_context, candidate_drugs, rule_evidence)
        )

    def review_with_critique(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        rule_evidence: list[RuleEvidence],
        critique: str,
        round_number: int = 2,
    ) -> AgentOpinion:
        if self.catalog.is_loaded():
            return self._review_from_catalog(candidate_drugs, debate_round=round_number)
        from src.prompts import REVISION_SUFFIX

        user = self.build_user_input(patient_context, candidate_drugs, rule_evidence)
        user += REVISION_SUFFIX.format(round_number=round_number, critique=critique)
        data = self.llm.chat_json(self.system_prompt, user)
        return self._normalize_llm_opinion(self._parse_opinion(data, debate_round=round_number))

    def _resolve_drug(self, drug: CandidateDrug) -> HospitalDrug | None:
        if drug.hospital_drug_id:
            record = self.catalog.get_by_id(drug.hospital_drug_id)
            if record is not None:
                return record
        return self.catalog.resolve_by_name(drug.name or drug.ingredient)

    def _review_from_catalog(
        self,
        candidate_drugs: list[CandidateDrug],
        *,
        debate_round: int = 1,
    ) -> AgentOpinion:
        reasons: list[str] = []
        alternatives: list[str] = []
        evidence: list[str] = []
        unknown_drugs: list[str] = []
        block = False
        risk = "low"

        for drug in candidate_drugs:
            label = (drug.name or drug.ingredient or "未知药品").strip()
            record = self._resolve_drug(drug)
            if record is None:
                unknown_drugs.append(label)
                reasons.append(f"{label} 未匹配院药品目录，需人工核对可开品种")
                if risk == "low":
                    risk = "medium"
                continue

            evidence.append(
                f"formulary:{record.hospital_drug_id}:in_formulary={int(record.in_formulary)}:"
                f"in_stock={int(record.in_stock)}"
            )

            if not record.in_formulary:
                block = True
                risk = "high"
                reasons.append(f"{record.display_name}（{record.hospital_drug_id}）不在院基本目录")
                for alt in self.catalog.list_alternatives(record.hospital_drug_id):
                    if alt.in_formulary and alt.in_stock:
                        alternatives.append(
                            f"{alt.display_name}（{alt.hospital_drug_id}，目录内·有货）"
                        )
                continue

            if not record.in_stock:
                in_stock_alts = [
                    alt
                    for alt in self.catalog.list_alternatives(record.hospital_drug_id)
                    if alt.in_formulary and alt.in_stock
                ]
                reasons.append(f"{record.display_name}（{record.hospital_drug_id}）当前缺货")
                if in_stock_alts:
                    if risk == "low":
                        risk = "medium"
                    for alt in in_stock_alts:
                        alternatives.append(
                            f"{alt.display_name}（{alt.hospital_drug_id}，目录内·有货）"
                        )
                else:
                    block = True
                    risk = "high"
                    reasons.append(
                        f"{record.display_name} 缺货且目录内无可用替代，暂无法调配"
                    )
                continue

            reasons.append(
                f"{record.display_name}（{record.hospital_drug_id}）在院目录内，当前有库存"
            )

        alternatives = list(dict.fromkeys(alternatives))

        if not candidate_drugs:
            summary = "无候选药物需核对院目录与库存。"
        elif block:
            summary = "存在非目录品种或无法调配的缺货，请改用院内可开替代。"
        elif alternatives:
            summary = "部分候选品种缺货或非目录，已列出院内可调配替代。"
        elif unknown_drugs:
            summary = "部分品种未匹配院目录，需人工确认可开品种与库存。"
        else:
            summary = "候选药物均在院目录内且库存可调配；临床安全性由临床药师/专科评估。"

        return AgentOpinion(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            role=self.role,
            risk_level=risk,
            block_decision=block,
            reasons=reasons,
            alternatives=alternatives,
            need_clarification=bool(unknown_drugs),
            clarification_targets=unknown_drugs,
            confidence=0.95 if not unknown_drugs else 0.75,
            evidence_cited=evidence,
            summary=summary,
            debate_round=debate_round,
        )

    def _normalize_llm_opinion(self, opinion: AgentOpinion) -> AgentOpinion:
        """When catalog unavailable, prevent LLM from acting as clinical pharmacist."""
        opinion.evidence_cited = [
            e for e in opinion.evidence_cited if e.startswith("formulary:")
        ]
        if opinion.block_decision and not any(
            "目录" in r or "缺货" in r or "库存" in r or "调配" in r for r in opinion.reasons
        ):
            opinion.block_decision = False
            opinion.risk_level = "low"
            opinion.reasons = [
                "（已忽略非库管职责的临床阻断理由）仅依据院目录/库存时无法阻断",
                *opinion.reasons,
            ]
        return opinion
