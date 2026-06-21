"""Critic agent — adversarial review of multi-agent opinions (ClinicalPilot critic pattern)."""
from __future__ import annotations

from src.llm.client import LLMClient
from src.prompts import CRITIC_SYSTEM_PROMPT, pretty_json
from src.schemas import (
    AgentOpinion,
    CandidateDrug,
    CriticOutput,
    PatientContext,
    RuleEvidence,
)


class CriticAgent:
    agent_id = "critic"
    agent_name = "对抗审查员"
    role = "识别分歧、低置信度与规则遗漏"

    def __init__(self, llm: LLMClient, confidence_threshold: float = 0.75) -> None:
        self.llm = llm
        self.confidence_threshold = confidence_threshold

    def review(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        opinions: list[AgentOpinion],
        rule_evidence: list[RuleEvidence],
        round_number: int,
    ) -> CriticOutput:
        deterministic = self._deterministic_checks(opinions, rule_evidence)
        payload = {
            "round": round_number,
            "patient_context": patient_context.model_dump(),
            "candidate_drugs": [d.model_dump() for d in candidate_drugs],
            "agent_opinions": [o.model_dump() for o in opinions],
            "rule_evidence": [e.model_dump() for e in rule_evidence],
            "deterministic_findings": deterministic,
        }
        data = self.llm.chat_json(CRITIC_SYSTEM_PROMPT, pretty_json(payload))
        if data:
            return self._merge(data, deterministic)
        return self._from_deterministic(deterministic, round_number)

    def _deterministic_checks(
        self,
        opinions: list[AgentOpinion],
        rule_evidence: list[RuleEvidence],
    ) -> dict:
        blocks = {o.agent_id: o.block_decision for o in opinions}
        risks = {o.agent_id: o.risk_level for o in opinions}
        low_conf = [o.agent_id for o in opinions if o.confidence < self.confidence_threshold]
        block_split = len(set(blocks.values())) > 1
        risk_split = len(set(risks.values())) > 1

        cited_rules = {rid for o in opinions for rid in o.evidence_cited}
        missed_rules = [e.rule_id for e in rule_evidence if e.rule_id not in cited_rules]

        dissent: list[str] = []
        if block_split:
            dissent.append(
                "阻断意见不一致："
                + ", ".join(f"{aid}={'block' if v else 'allow'}" for aid, v in blocks.items())
            )
        if risk_split:
            dissent.append(
                "风险等级不一致："
                + ", ".join(f"{aid}={v}" for aid, v in risks.items())
            )
        for aid in low_conf:
            op = next(o for o in opinions if o.agent_id == aid)
            dissent.append(f"{aid} 置信度过低 ({op.confidence:.2f} < {self.confidence_threshold})")

        return {
            "block_split": block_split,
            "risk_split": risk_split,
            "low_confidence_agents": low_conf,
            "missed_rule_ids": missed_rules,
            "dissent_log": dissent,
        }

    def _merge(self, data: dict, deterministic: dict) -> CriticOutput:
        dissent = list(dict.fromkeys(
            list(data.get("dissent_log", [])) + deterministic.get("dissent_log", [])
        ))
        low_conf = list(dict.fromkeys(
            list(data.get("low_confidence_agents", [])) + deterministic.get("low_confidence_agents", [])
        ))
        consensus = bool(data.get("consensus_reached", False))
        if deterministic["block_split"] or deterministic["risk_split"] or low_conf:
            consensus = False

        return CriticOutput(
            round_number=int(data.get("round_number", 0)),
            ehr_contradictions=list(data.get("ehr_contradictions", [])),
            evidence_gaps=list(data.get("evidence_gaps", [])) + [
                f"规则 {rid} 未被 Agent 引用" for rid in deterministic.get("missed_rule_ids", [])
            ],
            safety_misses=list(data.get("safety_misses", [])),
            overall_assessment=str(data.get("overall_assessment", "")),
            consensus_reached=consensus,
            dissent_log=dissent,
            low_confidence_agents=low_conf,
            min_confidence=float(data.get("min_confidence", 0.0)),
        )

    def _from_deterministic(self, deterministic: dict, round_number: int) -> CriticOutput:
        dissent = deterministic.get("dissent_log", [])
        consensus = not dissent
        return CriticOutput(
            round_number=round_number,
            evidence_gaps=[f"规则 {rid} 未被 Agent 引用" for rid in deterministic.get("missed_rule_ids", [])],
            overall_assessment="Critic 确定性审查完成。",
            consensus_reached=consensus,
            dissent_log=dissent,
            low_confidence_agents=deterministic.get("low_confidence_agents", []),
        )
