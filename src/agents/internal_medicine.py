from __future__ import annotations

from src.agents.base import LLMAgent
from src.agents.role_evidence import (
    filter_attending_evidence,
    opinion_from_evidence,
    scoped_user_payload,
    strip_foreign_evidence_citations,
)
from src.llm.client import LLMClient
from src.prompts import ATTENDING_SYSTEM_PROMPT, pretty_json
from src.schemas import AgentOpinion, CandidateDrug, DiagnosisItem, PatientContext, RuleEvidence

_ATTENDING_INSTRUCTION = (
    "你是内科主治，仅审查候选药物与诊断/适应证是否匹配、off-label 与整体临床路径。"
    "不要写 DDI/CYP、过敏、库存/formulary、妊娠分级等内容。"
    "若无临床场景规则命中，block_decision 应为 false。"
)

_FOREIGN_MARKERS = (
    "ddi_",
    "cyp3a4",
    "药物相互作用",
    "横纹肌",
    "过敏",
    "formulary",
    "库存",
    "alg_",
)


class InternalMedicineAgent(LLMAgent):
    agent_id = "internal_medicine"
    agent_name = "内科主治"
    role = "适应证与疾病-药物匹配审查"
    system_prompt = ATTENDING_SYSTEM_PROMPT

    def __init__(self, llm: LLMClient, system_prompt: str | None = None) -> None:
        super().__init__(llm, system_prompt=system_prompt)

    def build_user_input(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        rule_evidence: list[RuleEvidence],
    ) -> str:
        scoped = filter_attending_evidence(rule_evidence)
        diagnoses = [d.model_dump() for d in patient_context.diagnoses]
        return pretty_json(
            scoped_user_payload(
                patient_context,
                candidate_drugs,
                scoped,
                instruction=_ATTENDING_INSTRUCTION,
                extra={
                    "diagnoses_focus": diagnoses,
                    "symptoms_or_complaints": patient_context.symptoms_or_complaints,
                },
            )
        )

    def review(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        rule_evidence: list[RuleEvidence],
    ) -> AgentOpinion:
        scoped = filter_attending_evidence(rule_evidence)
        if scoped:
            return opinion_from_evidence(
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                role=self.role,
                evidence=scoped,
                evidence_prefix="attending",
                debate_round=1,
            )
        return self._empty_opinion(patient_context, candidate_drugs, debate_round=1)

    def review_with_critique(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        rule_evidence: list[RuleEvidence],
        critique: str,
        round_number: int = 2,
    ) -> AgentOpinion:
        scoped = filter_attending_evidence(rule_evidence)
        if scoped:
            return opinion_from_evidence(
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                role=self.role,
                evidence=scoped,
                evidence_prefix="attending",
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
            evidence_prefix="attending",
            foreign_markers=_FOREIGN_MARKERS,
        )

    def _empty_opinion(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        *,
        debate_round: int,
    ) -> AgentOpinion:
        diagnoses = self._diagnosis_labels(patient_context.diagnoses)
        if not diagnoses and candidate_drugs:
            return AgentOpinion(
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                role=self.role,
                risk_level="medium",
                block_decision=False,
                reasons=["诊断信息缺失，无法评估候选药物适应证匹配。"],
                alternatives=[],
                need_clarification=True,
                clarification_targets=["diagnoses"],
                confidence=0.85,
                evidence_cited=[],
                summary="请先补充主要诊断后再评估适应证与 off-label 风险；药物相互作用由临床药师评估。",
                debate_round=debate_round,
            )

        drug_labels = ", ".join(d.name or d.ingredient for d in candidate_drugs[:3] if d.name or d.ingredient)
        diag_text = "、".join(diagnoses[:4]) if diagnoses else "（诊断未结构化）"
        return AgentOpinion(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            role=self.role,
            risk_level="low",
            block_decision=False,
            reasons=["规则库未命中临床场景规则（如多重用药、跌倒风险等）。"],
            alternatives=[],
            need_clarification=False,
            clarification_targets=[],
            confidence=0.9,
            evidence_cited=[],
            summary=(
                f"从适应证/临床路径看，候选用药（{drug_labels or '—'}）需与诊断（{diag_text}）人工匹配；"
                "未见规则库场景阻断。DDI 与过敏分别由临床药师、过敏专员评估。"
            ),
            debate_round=debate_round,
        )

    @staticmethod
    def _diagnosis_labels(diagnoses: list[DiagnosisItem]) -> list[str]:
        return [d.name for d in diagnoses if d.name]
