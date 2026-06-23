"""Department-specific specialist agents activated by dept context and drug patterns."""

from __future__ import annotations

from src.agents.base import LLMAgent
from src.agents.registry import get_agent_registry
from src.agents.role_evidence import (
    filter_department_evidence,
    opinion_from_evidence,
    scoped_user_payload,
    strip_foreign_evidence_citations,
)
from src.department.context import DepartmentContext
from src.llm.client import LLMClient
from src.prompts import pretty_json
from src.schemas import AgentOpinion, CandidateDrug, PatientContext, RuleEvidence
from src.utils import normalize_text

_FOREIGN_MARKERS = (
    "ddi_",
    "cyp3a4",
    "药物相互作用",
    "横纹肌",
    "alg_",
    "formulary",
    "库存",
)


class DepartmentSpecialistAgent(LLMAgent):
    """Configurable department agent — agent_id set at construction from registry."""

    def __init__(
        self,
        llm: LLMClient,
        agent_id: str,
        agent_name: str,
        role: str,
        system_prompt: str | None = None,
        *,
        department: str = "",
        common_indications: list[str] | None = None,
        priority_categories: list[str] | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.role = role
        self.system_prompt = system_prompt or ""
        self.department = department
        self.common_indications = list(common_indications or [])
        self.priority_categories = list(priority_categories or [])
        super().__init__(llm, system_prompt=system_prompt)

    @staticmethod
    def should_activate(
        agent_id: str,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        department_context: DepartmentContext | None = None,
    ) -> bool:
        registry = get_agent_registry()
        spec = registry.get_department_agent_spec(agent_id)
        if not spec:
            return False
        return registry.should_activate_department_agent(
            spec,
            patient_context,
            candidate_drugs,
            department_context,
        )

    def _scoped_evidence(self, rule_evidence: list[RuleEvidence]) -> list[RuleEvidence]:
        return filter_department_evidence(rule_evidence, self.priority_categories)

    def build_user_input(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        rule_evidence: list[RuleEvidence],
    ) -> str:
        scoped = self._scoped_evidence(rule_evidence)
        instruction = (
            f"你是{self.agent_name}（{self.department or '科室专科'}），"
            f"仅审查本科室常见适应证（{', '.join(self.common_indications[:6]) or '见 common_indications'}）"
            "与科室相关场景/人群规则。"
            "不要重复 DDI、过敏、库存/formulary 审查（已由其他 Agent 负责）。"
        )
        return pretty_json(
            scoped_user_payload(
                patient_context,
                candidate_drugs,
                scoped,
                instruction=instruction,
                extra={"common_indications": self.common_indications},
            )
        )

    def review(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        rule_evidence: list[RuleEvidence],
    ) -> AgentOpinion:
        scoped = self._scoped_evidence(rule_evidence)
        if scoped:
            return opinion_from_evidence(
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                role=self.role,
                evidence=scoped,
                evidence_prefix=f"dept:{self.agent_id}",
                debate_round=1,
            )
        return self._empty_opinion(candidate_drugs, debate_round=1)

    def review_with_critique(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        rule_evidence: list[RuleEvidence],
        critique: str,
        round_number: int = 2,
    ) -> AgentOpinion:
        scoped = self._scoped_evidence(rule_evidence)
        if scoped:
            return opinion_from_evidence(
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                role=self.role,
                evidence=scoped,
                evidence_prefix=f"dept:{self.agent_id}",
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
            evidence_prefix=f"dept:{self.agent_id}",
            foreign_markers=_FOREIGN_MARKERS,
        )

    def _empty_opinion(
        self,
        candidate_drugs: list[CandidateDrug],
        *,
        debate_round: int,
    ) -> AgentOpinion:
        drug_blob = normalize_text(
            " ".join(f"{d.name} {d.ingredient}" for d in candidate_drugs)
        )
        indication_hit = any(
            normalize_text(ind) and normalize_text(ind) in drug_blob
            for ind in self.common_indications
        )
        dept_label = self.department or "本科室"
        indications = "、".join(self.common_indications[:4]) or "常见专科病种"
        summary = (
            f"从{dept_label}专科路径看，候选用药与常见适应证（{indications}）"
            + ("存在潜在关联，需结合病历人工确认。" if indication_hit else "未见明显专科规则命中，需人工确认适应证。")
            + " DDI/过敏/库存由其他 Agent 评估。"
        )
        return AgentOpinion(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            role=self.role,
            risk_level="low",
            block_decision=False,
            reasons=[f"{dept_label}规则库未命中科室场景/人群规则。"],
            alternatives=[],
            need_clarification=not indication_hit and bool(candidate_drugs),
            clarification_targets=["diagnoses"] if not indication_hit else [],
            confidence=0.86,
            evidence_cited=[],
            summary=summary,
            debate_round=debate_round,
        )
