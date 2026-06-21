from __future__ import annotations

from src.llm.client import LLMClient
from src.prompts import CHIEF_SYSTEM_PROMPT, pretty_json
from src.schemas import AgentOpinion, ArbitrationResult, ReviewOutput, RuleEvidence


RISK_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3, "unknown": 4}


class ChiefReviewerAgent:
    """会诊主席 — 汇总各 Agent 意见，规则 evidence 不可被覆盖。"""

    agent_id = "chief_reviewer"
    agent_name = "会诊主席"
    role = "冲突仲裁与最终建议"

    def __init__(self, llm: LLMClient, rule_strict: bool = True) -> None:
        self.llm = llm
        self.rule_strict = rule_strict

    def arbitrate(
        self,
        agent_opinions: list[AgentOpinion],
        rule_output: ReviewOutput,
    ) -> ArbitrationResult:
        payload = {
            "rule_output": rule_output.model_dump(),
            "agent_opinions": [o.model_dump() for o in agent_opinions],
        }
        data = self.llm.chat_json(CHIEF_SYSTEM_PROMPT, pretty_json(payload))
        if data:
            return self._merge_llm_result(data, agent_opinions, rule_output)
        return self._deterministic_arbitrate(agent_opinions, rule_output)

    def _merge_llm_result(
        self,
        data: dict,
        agent_opinions: list[AgentOpinion],
        rule_output: ReviewOutput,
    ) -> ArbitrationResult:
        result = self._deterministic_arbitrate(agent_opinions, rule_output)
        if not self.rule_strict:
            result.consensus_risk_level = data.get("consensus_risk_level", result.consensus_risk_level)
            result.consensus_block_decision = bool(
                data.get("consensus_block_decision", result.consensus_block_decision)
            )
        result.final_recommendation = data.get("final_recommendation", result.final_recommendation)
        result.arbitration_notes = data.get("arbitration_notes", result.arbitration_notes)
        result.conflict_detected = bool(data.get("conflict_detected", result.conflict_detected))
        return result

    def _deterministic_arbitrate(
        self,
        agent_opinions: list[AgentOpinion],
        rule_output: ReviewOutput,
    ) -> ArbitrationResult:
        risk = rule_output.risk_level
        block = rule_output.block_decision
        reasons = list(rule_output.risk_reasons)
        alternatives = list(rule_output.alternative_suggestions)
        clarification_targets = list(rule_output.clarification_targets)
        need_clarification = rule_output.need_clarification
        dissenting: list[AgentOpinion] = []
        conflict = False

        for opinion in agent_opinions:
            if opinion.block_decision != block or opinion.risk_level != risk:
                if not (self.rule_strict and rule_output.risk_level == "high"):
                    conflict = True
                    dissenting.append(opinion)
            if RISK_ORDER.get(opinion.risk_level, 0) > RISK_ORDER.get(risk, 0):
                if not (self.rule_strict and rule_output.risk_level == "high"):
                    risk = opinion.risk_level
            if opinion.block_decision and opinion.agent_id in {"clinical_pharmacist", "allergy_specialist"}:
                block = True
            reasons.extend(opinion.reasons)
            alternatives.extend(opinion.alternatives)
            if opinion.need_clarification:
                need_clarification = True
                clarification_targets.extend(opinion.clarification_targets)

        if self.rule_strict and rule_output.risk_level == "high":
            risk = "high"
            block = True

        if block:
            final = "综合会诊意见：当前方案存在安全风险，建议阻断并考虑替代方案或人工复核。"
        elif need_clarification:
            final = "综合会诊意见：关键信息不足，请先补充后再做最终用药决策。"
        else:
            final = "综合会诊意见：未发现需阻断的高风险问题，可在常规监测下继续评估。"

        if rule_output.final_recommendation:
            final = rule_output.final_recommendation

        return ArbitrationResult(
            consensus_risk_level=risk,
            consensus_block_decision=block,
            agent_opinions=agent_opinions,
            dissenting_opinions=dissenting,
            conflict_detected=conflict,
            arbitration_notes="规则 evidence 优先；临床药师/过敏专员任一阻断则默认阻断。",
            final_recommendation=final,
            need_clarification=need_clarification,
            clarification_targets=list(dict.fromkeys(clarification_targets)),
            rule_evidence=rule_output.evidence,
        )
