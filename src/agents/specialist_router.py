from __future__ import annotations

from src.agents.base import LLMAgent
from src.agents.registry import get_agent_registry
from src.agents.role_evidence import (
    filter_specialist_evidence,
    opinion_from_evidence,
    scoped_user_payload,
    strip_foreign_evidence_citations,
)
from src.llm.client import LLMClient
from src.prompts import SPECIALIST_SYSTEM_PROMPT, pretty_json
from src.schemas import AgentOpinion, CandidateDrug, PatientContext, RuleEvidence

_SPECIALIST_INSTRUCTION = (
    "你是专科医生，仅审查妊娠/哺乳、老年、肝肾功能等特殊人群禁忌与专科场景规则。"
    "不要写 DDI/CYP、一般适应证、过敏、库存/formulary 等内容。"
    "若无专科规则命中，block_decision 应为 false，risk_level 通常为 low。"
)

_FOREIGN_MARKERS = (
    "ddi_",
    "cyp3a4",
    "药物相互作用",
    "formulary",
    "库存",
    "适应证",
    "alg_",
)


class SpecialistAgent(LLMAgent):
    agent_id = "specialist"
    agent_name = "专科医生"
    role = "专科禁忌审查（妊娠/抗凝/感染等）"
    system_prompt = SPECIALIST_SYSTEM_PROMPT

    def __init__(self, llm: LLMClient, system_prompt: str | None = None) -> None:
        super().__init__(llm, system_prompt=system_prompt)

    @staticmethod
    def should_activate(patient_context: PatientContext, candidate_drugs: list[CandidateDrug]) -> bool:
        return get_agent_registry().should_activate_specialist(patient_context, candidate_drugs)

    def build_user_input(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        rule_evidence: list[RuleEvidence],
    ) -> str:
        scoped = filter_specialist_evidence(rule_evidence)
        return pretty_json(
            scoped_user_payload(
                patient_context,
                candidate_drugs,
                scoped,
                instruction=_SPECIALIST_INSTRUCTION,
                extra={
                    "pregnancy_status": patient_context.pregnancy_status,
                    "lactation_status": patient_context.lactation_status,
                    "egfr": patient_context.egfr,
                },
            )
        )

    def review(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        rule_evidence: list[RuleEvidence],
    ) -> AgentOpinion:
        scoped = filter_specialist_evidence(rule_evidence)
        if scoped:
            return opinion_from_evidence(
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                role=self.role,
                evidence=scoped,
                evidence_prefix="specialist",
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
        scoped = filter_specialist_evidence(rule_evidence)
        if scoped:
            return opinion_from_evidence(
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                role=self.role,
                evidence=scoped,
                evidence_prefix="specialist",
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
            evidence_prefix="specialist",
            foreign_markers=_FOREIGN_MARKERS,
        )

    def _empty_opinion(self, *, debate_round: int) -> AgentOpinion:
        return AgentOpinion(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            role=self.role,
            risk_level="low",
            block_decision=False,
            reasons=["规则库未命中特殊人群或专科场景禁忌。"],
            alternatives=[],
            need_clarification=False,
            clarification_targets=[],
            confidence=0.88,
            evidence_cited=[],
            summary="从专科人群/场景维度未见规则库阻断依据；DDI 与适应证分别由临床药师、内科主治评估。",
            debate_round=debate_round,
        )
