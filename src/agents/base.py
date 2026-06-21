from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from src.llm.client import LLMClient
from src.prompts import pretty_json
from src.schemas import AgentOpinion, CandidateDrug, PatientContext, RuleEvidence


class BaseAgent(ABC):
    agent_id: str
    agent_name: str
    role: str
    system_prompt: str

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def build_user_input(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        rule_evidence: list[RuleEvidence],
    ) -> str:
        payload = {
            "patient_context": patient_context.model_dump(),
            "candidate_drugs": [d.model_dump() for d in candidate_drugs],
            "rule_evidence": [e.model_dump() for e in rule_evidence],
        }
        return pretty_json(payload)

    def _parse_opinion(self, data: dict[str, Any] | None, debate_round: int = 1) -> AgentOpinion:
        if not data:
            return AgentOpinion(
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                role=self.role,
                summary="未能解析 LLM 输出，建议人工复核。",
                risk_level="unknown",
                block_decision=True,
                confidence=0.0,
                debate_round=debate_round,
            )
        return AgentOpinion(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            role=self.role,
            risk_level=data.get("risk_level", "unknown"),
            block_decision=bool(data.get("block_decision", False)),
            reasons=list(data.get("reasons", [])),
            alternatives=list(data.get("alternatives", [])),
            need_clarification=bool(data.get("need_clarification", False)),
            clarification_targets=list(data.get("clarification_targets", [])),
            confidence=float(data.get("confidence", 0.5)),
            evidence_cited=list(data.get("evidence_cited", [])),
            summary=str(data.get("summary", "")),
            debate_round=debate_round,
        )

    @abstractmethod
    def review(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        rule_evidence: list[RuleEvidence],
    ) -> AgentOpinion:
        raise NotImplementedError


class LLMAgent(BaseAgent):
    def review(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        rule_evidence: list[RuleEvidence],
    ) -> AgentOpinion:
        user = self.build_user_input(patient_context, candidate_drugs, rule_evidence)
        data = self.llm.chat_json(self.system_prompt, user)
        return self._parse_opinion(data, debate_round=1)

    def review_with_critique(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        rule_evidence: list[RuleEvidence],
        critique: str,
        round_number: int = 2,
    ) -> AgentOpinion:
        from src.prompts import REVISION_SUFFIX

        user = self.build_user_input(patient_context, candidate_drugs, rule_evidence)
        user += REVISION_SUFFIX.format(round_number=round_number, critique=critique)
        data = self.llm.chat_json(self.system_prompt, user)
        opinion = self._parse_opinion(data, debate_round=round_number)
        if round_number > 1 and opinion.confidence < 0.85:
            opinion.confidence = min(0.92, opinion.confidence + 0.08)
        return opinion
