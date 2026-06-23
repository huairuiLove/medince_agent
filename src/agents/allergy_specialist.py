from __future__ import annotations

from src.agents.base import LLMAgent
from src.llm.client import LLMClient
from src.prompts import ALLERGY_SYSTEM_PROMPT, pretty_json
from src.schemas import AgentOpinion, CandidateDrug, PatientContext, RuleEvidence
from src.utils import normalize_text

_ALLERGY_CATEGORIES = frozenset({"allergy_contraindication", "adr", "adr_history"})
_EXPLICIT_NO_ALLERGY_TERMS = (
    "nkda",
    "no known drug allergy",
    "no known allergy",
    "denies allergy",
    "无过敏",
    "无已知过敏",
    "否认过敏",
    "未发现过敏",
)
_NON_ALLERGY_MARKERS = (
    "ddi_",
    "cyp3a4",
    "药物相互作用",
    "横纹肌",
    "联用可显著",
    "肌酸激酶",
    "剂量",
    "egfr",
    "致畸",
    "妊娠",
)
_ALLERGY_CLARIFY_DRUG_TERMS = (
    "amoxicillin",
    "ampicillin",
    "penicillin",
    "cephalexin",
    "ceftriaxone",
    "cef",
    "阿莫西林",
    "氨苄西林",
    "青霉素",
    "头孢",
)


def filter_allergy_evidence(rule_evidence: list[RuleEvidence]) -> list[RuleEvidence]:
    return [
        item
        for item in rule_evidence
        if item.category in _ALLERGY_CATEGORIES or item.rule_id.startswith("alg_")
    ]


class AllergySpecialistAgent(LLMAgent):
    agent_id = "allergy_specialist"
    agent_name = "过敏专员"
    role = "过敏史与交叉过敏审查"
    system_prompt = ALLERGY_SYSTEM_PROMPT

    def __init__(self, llm: LLMClient, system_prompt: str | None = None) -> None:
        super().__init__(llm, system_prompt=system_prompt)

    def build_user_input(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        rule_evidence: list[RuleEvidence],
    ) -> str:
        allergy_evidence = filter_allergy_evidence(rule_evidence)
        payload = {
            "patient_context": patient_context.model_dump(),
            "candidate_drugs": [d.model_dump() for d in candidate_drugs],
            "rule_evidence": [e.model_dump() for e in allergy_evidence],
            "instruction": (
                "仅审查过敏史、交叉过敏与既往 ADR；"
                "不要引用 DDI/剂量/适应证/妊娠/库存规则；"
                "若无过敏禁忌，block_decision 应为 false，risk_level 通常为 low。"
            ),
        }
        return pretty_json(payload)

    def review(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        rule_evidence: list[RuleEvidence],
    ) -> AgentOpinion:
        allergy_evidence = filter_allergy_evidence(rule_evidence)
        if self._should_review_deterministically(patient_context, candidate_drugs, allergy_evidence):
            return self._review_deterministic(
                patient_context, candidate_drugs, allergy_evidence, debate_round=1
            )
        opinion = super().review(patient_context, candidate_drugs, rule_evidence)
        return self._normalize_opinion(opinion, allergy_evidence)

    def review_with_critique(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        rule_evidence: list[RuleEvidence],
        critique: str,
        round_number: int = 2,
    ) -> AgentOpinion:
        from src.prompts import REVISION_SUFFIX

        allergy_evidence = filter_allergy_evidence(rule_evidence)
        if self._should_review_deterministically(patient_context, candidate_drugs, allergy_evidence):
            return self._review_deterministic(
                patient_context, candidate_drugs, allergy_evidence, debate_round=round_number
            )

        user = self.build_user_input(patient_context, candidate_drugs, rule_evidence)
        user += REVISION_SUFFIX.format(round_number=round_number, critique=critique)
        data = self.llm.chat_json(self.system_prompt, user)
        opinion = self._parse_opinion(data, debate_round=round_number)
        if round_number > 1 and opinion.confidence < 0.85:
            opinion.confidence = min(0.92, opinion.confidence + 0.08)
        return self._normalize_opinion(opinion, allergy_evidence)

    @staticmethod
    def _allergies_explicitly_none(allergies: list[str]) -> bool:
        blob = normalize_text(" ".join(allergies))
        return any(term in blob for term in _EXPLICIT_NO_ALLERGY_TERMS)

    @staticmethod
    def _has_specific_allergies(patient_context: PatientContext) -> bool:
        allergies = patient_context.allergies
        if not allergies:
            return False
        return not AllergySpecialistAgent._allergies_explicitly_none(allergies)

    @staticmethod
    def _needs_allergy_clarification(
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
    ) -> bool:
        if patient_context.allergies:
            return False
        if "allergies" in patient_context.missing_fields:
            return True
        drug_blob = normalize_text(
            " ".join(
                f"{d.name} {d.ingredient}"
                for d in candidate_drugs + list(patient_context.current_medications)
            )
        )
        return any(term in drug_blob for term in _ALLERGY_CLARIFY_DRUG_TERMS)

    @classmethod
    def _should_review_deterministically(
        cls,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        allergy_evidence: list[RuleEvidence],
    ) -> bool:
        if allergy_evidence:
            return True
        if cls._has_specific_allergies(patient_context):
            return False
        if cls._allergies_explicitly_none(patient_context.allergies):
            return True
        if cls._needs_allergy_clarification(patient_context, candidate_drugs):
            return True
        return True

    def _review_deterministic(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        allergy_evidence: list[RuleEvidence],
        *,
        debate_round: int = 1,
    ) -> AgentOpinion:
        if allergy_evidence:
            return self._review_from_allergy_evidence(allergy_evidence, debate_round=debate_round)

        if self._needs_allergy_clarification(patient_context, candidate_drugs):
            return AgentOpinion(
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                role=self.role,
                risk_level="medium",
                block_decision=False,
                reasons=["过敏史缺失，无法排除交叉过敏风险。"],
                alternatives=[],
                need_clarification=True,
                clarification_targets=["allergies"],
                confidence=0.85,
                evidence_cited=[],
                summary="请先补充患者过敏史后再评估交叉过敏；非过敏维度风险由临床药师评估。",
                debate_round=debate_round,
            )

        return AgentOpinion(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            role=self.role,
            risk_level="low",
            block_decision=False,
            reasons=["未发现过敏史与候选药物交叉过敏或既往 ADR 冲突。"],
            alternatives=[],
            need_clarification=False,
            clarification_targets=[],
            confidence=0.92,
            evidence_cited=[],
            summary=(
                "从过敏维度未见阻断依据"
                + (
                    "（患者否认/无已知药物过敏）。"
                    if self._allergies_explicitly_none(patient_context.allergies)
                    else "。"
                )
                + "药物相互作用等风险由临床药师评估。"
            ),
            debate_round=debate_round,
        )

    def _review_from_allergy_evidence(
        self,
        allergy_evidence: list[RuleEvidence],
        *,
        debate_round: int = 1,
    ) -> AgentOpinion:
        risk_order = {"high": 4, "medium": 3, "low": 2, "unknown": 1, "none": 0}
        top = max(allergy_evidence, key=lambda item: risk_order.get(item.risk_level, 0))
        block = any(item.risk_level == "high" for item in allergy_evidence)
        reasons = [item.summary for item in allergy_evidence if item.summary]
        alternatives: list[str] = []
        for item in allergy_evidence:
            alternatives.extend(item.alternatives)
        clarification_targets: list[str] = []
        for item in allergy_evidence:
            clarification_targets.extend(item.clarification_fields)

        return AgentOpinion(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            role=self.role,
            risk_level=top.risk_level,
            block_decision=block,
            reasons=reasons,
            alternatives=list(dict.fromkeys(alternatives)),
            need_clarification=bool(clarification_targets),
            clarification_targets=list(dict.fromkeys(clarification_targets)),
            confidence=0.95,
            evidence_cited=[f"allergy:{item.rule_id}" for item in allergy_evidence],
            summary=top.summary or "存在过敏禁忌，建议阻断或更换替代方案。",
            debate_round=debate_round,
        )

    def _normalize_opinion(
        self,
        opinion: AgentOpinion,
        allergy_evidence: list[RuleEvidence],
    ) -> AgentOpinion:
        allowed_rule_ids = {item.rule_id for item in allergy_evidence}
        opinion.evidence_cited = [
            item
            for item in opinion.evidence_cited
            if item.startswith("allergy:")
            or any(rule_id in item for rule_id in allowed_rule_ids)
        ]

        blob = normalize_text(
            " ".join(opinion.reasons + [opinion.summary] + opinion.evidence_cited)
        )
        if opinion.block_decision and any(marker in blob for marker in _NON_ALLERGY_MARKERS):
            opinion.block_decision = False
            if not allergy_evidence:
                opinion.risk_level = "low"
            opinion.reasons = [
                "（已忽略非过敏职责的 DDI/剂量等理由）",
                *opinion.reasons,
            ]
            if not opinion.summary.strip():
                opinion.summary = "未见过敏维度阻断依据；药物相互作用由临床药师评估。"
        return opinion
