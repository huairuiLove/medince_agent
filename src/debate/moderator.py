"""Moderator — MDAgents-style group synthesis before chief arbitration."""
from __future__ import annotations

from src.llm.client import LLMClient
from src.prompts import MODERATOR_SYSTEM_PROMPT, pretty_json
from src.schemas import AgentOpinion, CriticOutput, DebateRoundRecord, ModeratorSynthesis, RuleEvidence


class ModeratorAgent:
    """Synthesize multi-round debate into structured consensus brief for the chief."""

    agent_id = "moderator"
    agent_name = "会诊主持人"
    role = "汇总各轮辩论、标注一致与分歧"

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def synthesize(
        self,
        rounds: list[DebateRoundRecord],
        rule_evidence: list[RuleEvidence],
        safety_panel_summary: str = "",
    ) -> ModeratorSynthesis:
        payload = {
            "debate_rounds": [r.model_dump() for r in rounds],
            "rule_evidence": [e.model_dump() for e in rule_evidence],
            "safety_panel_summary": safety_panel_summary,
        }
        data = self.llm.chat_json(MODERATOR_SYSTEM_PROMPT, pretty_json(payload))
        if data:
            return ModeratorSynthesis(
                consistency_notes=list(data.get("consistency_notes", [])),
                conflict_notes=list(data.get("conflict_notes", [])),
                integration_summary=str(data.get("integration_summary", "")),
                recommended_risk_level=data.get("recommended_risk_level", "unknown"),
                recommended_block=bool(data.get("recommended_block", False)),
                majority_block_votes=int(data.get("majority_block_votes", 0)),
                total_agents=int(data.get("total_agents", 0)),
            )
        return self._deterministic_synthesis(rounds)

    @staticmethod
    def _deterministic_synthesis(rounds: list[DebateRoundRecord]) -> ModeratorSynthesis:
        if not rounds:
            return ModeratorSynthesis(integration_summary="无辩论轮次。")
        final = rounds[-1].agent_opinions
        block_votes = sum(1 for o in final if o.block_decision)
        high_risk = sum(1 for o in final if o.risk_level in {"high", "unknown"})
        conflicts = rounds[-1].critic_output.dissent_log if rounds[-1].critic_output else []

        risk = "high" if high_risk >= 2 else "unknown" if high_risk else "low"
        if any(o.risk_level == "high" for o in final):
            risk = "high"

        return ModeratorSynthesis(
            consistency_notes=[o.summary for o in final if not o.block_decision],
            conflict_notes=conflicts,
            integration_summary="主持人汇总：基于末轮专家意见与 Critic 分歧记录。",
            recommended_risk_level=risk,
            recommended_block=block_votes > len(final) // 2,
            majority_block_votes=block_votes,
            total_agents=len(final),
        )
