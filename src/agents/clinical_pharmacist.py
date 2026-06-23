from __future__ import annotations

from src.agents.base import LLMAgent
from src.agents.role_evidence import (
    filter_pharmacist_evidence,
    opinion_from_evidence,
    scoped_user_payload,
    strip_foreign_evidence_citations,
)
from src.llm.client import LLMClient
from src.prompts import PHARMACIST_SYSTEM_PROMPT, pretty_json
from src.schemas import AgentOpinion, CandidateDrug, PatientContext, RuleEvidence

_PHARMACIST_INSTRUCTION = (
    "你是临床药师，仅审查 DDI、重复用药、剂量/给药途径。"
    "不要写适应证匹配、过敏、库存/formulary、妊娠分级等内容。"
    "若无 rule_evidence，block_decision 应为 false，risk_level 通常为 low。"
)

_FOREIGN_MARKERS = (
    "过敏",
    "formulary",
    "库存",
    "适应证",
    "off-label",
    "妊娠",
    "致畸",
)


class ClinicalPharmacistAgent(LLMAgent):
    agent_id = "clinical_pharmacist"
    agent_name = "临床药师"
    role = "药物相互作用、剂量、重复用药审查"
    system_prompt = PHARMACIST_SYSTEM_PROMPT

    def __init__(self, llm: LLMClient, system_prompt: str | None = None) -> None:
        super().__init__(llm, system_prompt=system_prompt)

    def build_user_input(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        rule_evidence: list[RuleEvidence],
    ) -> str:
        scoped = filter_pharmacist_evidence(rule_evidence)
        return pretty_json(
            scoped_user_payload(
                patient_context,
                candidate_drugs,
                scoped,
                instruction=_PHARMACIST_INSTRUCTION,
            )
        )

    def review(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        rule_evidence: list[RuleEvidence],
    ) -> AgentOpinion:
        scoped = filter_pharmacist_evidence(rule_evidence)
        if scoped:
            return opinion_from_evidence(
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                role=self.role,
                evidence=scoped,
                evidence_prefix="pharmacist",
                debate_round=1,
            )
        return self._empty_opinion(debate_round=1)

    def review_with_critique(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        rule_evidence: list[RuleEvidence],
        critique: str,
        round_number: int = 2,
    ) -> AgentOpinion:
        scoped = filter_pharmacist_evidence(rule_evidence)
        if scoped:
            return opinion_from_evidence(
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                role=self.role,
                evidence=scoped,
                evidence_prefix="pharmacist",
                debate_round=round_number,
            )
        from src.prompts import REVISION_SUFFIX

        user = self.build_user_input(patient_context, candidate_drugs, rule_evidence)
        user += REVISION_SUFFIX.format(round_number=round_number, critique=critique)
        data = self.llm.chat_json(self.system_prompt, user)
        opinion = self._parse_opinion(data, debate_round=round_number)
        return strip_foreign_evidence_citations(
            opinion,
            {item.rule_id for item in scoped},
            evidence_prefix="pharmacist",
            foreign_markers=_FOREIGN_MARKERS,
        )

    def _empty_opinion(self, *, debate_round: int) -> AgentOpinion:
        return AgentOpinion(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            role=self.role,
            risk_level="low",
            block_decision=False,
            reasons=["规则库未命中 DDI 或重复用药。"],
            alternatives=[],
            need_clarification=False,
            clarification_targets=[],
            confidence=0.88,
            evidence_cited=[],
            summary="从药学相互作用/重复用药维度未见规则库阻断依据；剂量与肝肾功能调整需结合检验值人工复核。",
            debate_round=debate_round,
        )
