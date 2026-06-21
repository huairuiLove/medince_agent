"""Multi-round debate orchestrator — ClinicalPilot debate_engine + MDAgents moderator."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.agents.base import BaseAgent
from src.config import get_config
from src.debate.critic_agent import CriticAgent
from src.debate.moderator import ModeratorAgent
from src.debate.safety_panel import SafetyPanel
from src.llm.client import LLMClient
from src.logging_config import get_logger
from src.schemas import (
    AgentOpinion,
    CandidateDrug,
    CriticOutput,
    DebateResult,
    DebateRoundRecord,
    PatientContext,
    RuleEvidence,
    SafetyPanelResult,
)

logger = get_logger("debate.engine")


def format_critique(critic: CriticOutput) -> str:
    """Format critic output for agent revision prompts (ClinicalPilot pattern)."""
    parts: list[str] = []
    if critic.dissent_log:
        parts.append("分歧点：\n" + "\n".join(f"- {d}" for d in critic.dissent_log))
    if critic.evidence_gaps:
        parts.append("证据缺口：\n" + "\n".join(f"- {g}" for g in critic.evidence_gaps))
    if critic.safety_misses:
        parts.append("安全遗漏：\n" + "\n".join(f"- {m}" for m in critic.safety_misses))
    if critic.low_confidence_agents:
        parts.append(
            "低置信度 Agent："
            + ", ".join(critic.low_confidence_agents)
        )
    if critic.overall_assessment:
        parts.append(f"总体评估：{critic.overall_assessment}")
    return "\n\n".join(parts) if parts else "请复核上一轮意见并提高置信度。"


class DebateEngine:
    """
    Round 1: parallel independent agent review
    Round 2..N: Critic → revision with critique (max rounds configurable)
    Final: Moderator synthesis + Safety Panel (parallel to debate in ClinicalPilot)
    """

    def __init__(
        self,
        llm: LLMClient,
        agents: list[BaseAgent],
        safety_panel: SafetyPanel | None = None,
    ) -> None:
        cfg = get_config().get("debate", {})
        self.llm = llm
        self.agents = agents
        self.max_rounds = int(cfg.get("max_rounds", 3))
        self.confidence_threshold = float(cfg.get("confidence_threshold", 0.75))
        self.enabled = bool(cfg.get("enabled", True))
        self.flag_for_human = bool(cfg.get("flag_for_human_on_no_consensus", True))
        self.critic = CriticAgent(llm, confidence_threshold=self.confidence_threshold)
        self.moderator = ModeratorAgent(llm)
        self.safety_panel = safety_panel or SafetyPanel()

    def _run_agents(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        rule_evidence: list[RuleEvidence],
        critique: str = "",
        round_number: int = 1,
    ) -> list[AgentOpinion]:
        opinions: list[AgentOpinion] = []
        with ThreadPoolExecutor(max_workers=len(self.agents)) as pool:
            if critique:
                futures = {
                    pool.submit(
                        agent.review_with_critique,
                        patient_context,
                        candidate_drugs,
                        rule_evidence,
                        critique,
                        round_number,
                    ): agent
                    for agent in self.agents
                }
            else:
                futures = {
                    pool.submit(agent.review, patient_context, candidate_drugs, rule_evidence): agent
                    for agent in self.agents
                }
            for future in as_completed(futures):
                opinions.append(future.result())
        opinions.sort(key=lambda o: o.agent_id)
        return opinions

    def run(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        rule_evidence: list[RuleEvidence],
    ) -> tuple[list[AgentOpinion], DebateResult, SafetyPanelResult]:
        t0 = time.perf_counter()
        rounds: list[DebateRoundRecord] = []
        final_consensus = False
        flagged_for_human = False

        if not self.enabled or self.max_rounds < 1:
            opinions = self._run_agents(patient_context, candidate_drugs, rule_evidence)
            safety = self.safety_panel.run(patient_context, candidate_drugs)
            elapsed = (time.perf_counter() - t0) * 1000
            debate = DebateResult(
                enabled=False,
                rounds=[],
                final_opinions=opinions,
                final_consensus=True,
                flagged_for_human=False,
                min_confidence=min((o.confidence for o in opinions), default=1.0),
                duration_ms=elapsed,
            )
            return opinions, debate, safety

        opinions = self._run_agents(patient_context, candidate_drugs, rule_evidence, round_number=1)
        critic: CriticOutput | None = None

        for round_num in range(1, self.max_rounds + 1):
            logger.info("debate_round", extra={"round": round_num, "max": self.max_rounds})

            if round_num > 1:
                critique = format_critique(critic) if critic else ""
                opinions = self._run_agents(
                    patient_context,
                    candidate_drugs,
                    rule_evidence,
                    critique=critique,
                    round_number=round_num,
                )

            min_conf = min((o.confidence for o in opinions), default=1.0)
            critic = self.critic.review(
                patient_context,
                candidate_drugs,
                opinions,
                rule_evidence,
                round_number=round_num,
            )
            critic.min_confidence = min_conf
            critic.round_number = round_num

            rounds.append(
                DebateRoundRecord(
                    round_number=round_num,
                    agent_opinions=opinions,
                    critic_output=critic,
                    min_confidence=min_conf,
                )
            )

            if critic.consensus_reached and min_conf >= self.confidence_threshold:
                final_consensus = True
                logger.info("debate_consensus", extra={"round": round_num})
                break

            if round_num >= self.max_rounds:
                flagged_for_human = self.flag_for_human and not critic.consensus_reached
                logger.warning("debate_no_consensus", extra={"rounds": round_num})

        safety = self.safety_panel.run(patient_context, candidate_drugs)
        synthesis = self.moderator.synthesize(rounds, rule_evidence, safety.summary)
        elapsed = (time.perf_counter() - t0) * 1000

        debate = DebateResult(
            enabled=True,
            rounds=rounds,
            moderator_synthesis=synthesis,
            final_opinions=opinions,
            final_consensus=final_consensus,
            flagged_for_human=flagged_for_human,
            min_confidence=min((o.confidence for o in opinions), default=1.0),
            duration_ms=elapsed,
            llm_calls_estimate=len(rounds) * (len(self.agents) + 1) + 1,
        )
        return opinions, debate, safety
