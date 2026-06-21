"""Multi-agent drug safety review orchestrator."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from src.agents.allergy_specialist import AllergySpecialistAgent
from src.agents.chief_reviewer import ChiefReviewerAgent
from src.agents.clinical_pharmacist import ClinicalPharmacistAgent
from src.agents.coordinator import CoordinatorAgent
from src.agents.internal_medicine import InternalMedicineAgent
from src.agents.pharmacy_inventory import PharmacyInventoryAgent
from src.agents.specialist_router import SpecialistAgent
from src.config import get_config
from src.llm.client import get_llm_client
from src.review_engine import ReviewEngine
from src.schemas import (
    AgentOpinion,
    ArbitrationResult,
    CandidateDrug,
    ClarifyOutput,
    MultiReviewResponse,
    PatientContext,
    ReviewOutput,
)


class MultiAgentOrchestrator:
    def __init__(self) -> None:
        cfg = get_config()
        self.llm = get_llm_client()
        self.rule_strict = cfg.get("agents", {}).get("rule_strict", True)
        self.review_engine = ReviewEngine()
        self.pharmacist = ClinicalPharmacistAgent(self.llm)
        self.attending = InternalMedicineAgent(self.llm)
        self.allergy = AllergySpecialistAgent(self.llm)
        self.pharmacy = PharmacyInventoryAgent(self.llm)
        self.specialist = SpecialistAgent(self.llm)
        self.chief = ChiefReviewerAgent(self.llm, rule_strict=self.rule_strict)
        self.coordinator = CoordinatorAgent(self.llm)

    def _active_agents(self, patient_context: PatientContext, candidate_drugs: list[CandidateDrug]) -> list:
        agents = [self.pharmacist, self.attending, self.allergy, self.pharmacy]
        if SpecialistAgent.should_activate(patient_context, candidate_drugs):
            agents.append(self.specialist)
        return agents

    def _run_agents_parallel(
        self,
        agents: list,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        rule_evidence: list,
    ) -> list[AgentOpinion]:
        opinions: list[AgentOpinion] = []
        with ThreadPoolExecutor(max_workers=len(agents)) as pool:
            futures = {
                pool.submit(agent.review, patient_context, candidate_drugs, rule_evidence): agent
                for agent in agents
            }
            for future in as_completed(futures):
                opinions.append(future.result())
        opinions.sort(key=lambda o: o.agent_id)
        return opinions

    def run(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        unable_to_answer: bool = False,
        skip_clarify: bool = False,
    ) -> MultiReviewResponse:
        rule_output = self.review_engine.review(patient_context, candidate_drugs)
        agents = self._active_agents(patient_context, candidate_drugs)
        agent_opinions = self._run_agents_parallel(
            agents, patient_context, candidate_drugs, rule_output.evidence
        )
        arbitration = self.chief.arbitrate(agent_opinions, rule_output)

        clarify_output: ClarifyOutput | None = None
        final_recommendation = arbitration.final_recommendation

        review_for_clarify = ReviewOutput(
            risk_level=arbitration.consensus_risk_level,
            block_decision=arbitration.consensus_block_decision,
            risk_reasons=arbitration.final_recommendation.split("。")[:3],
            need_clarification=arbitration.need_clarification,
            clarification_targets=arbitration.clarification_targets,
            evidence=rule_output.evidence,
            final_recommendation=arbitration.final_recommendation,
        )

        if not skip_clarify and (arbitration.need_clarification or unable_to_answer):
            clarify_output = self.coordinator.clarify(
                patient_context, candidate_drugs, review_for_clarify, unable_to_answer=unable_to_answer
            )
            if clarify_output.conservative_advice:
                final_recommendation = clarify_output.conservative_advice.summary
            elif clarify_output.status == "need_user_input":
                final_recommendation = clarify_output.final_message

        return MultiReviewResponse(
            rule_output=rule_output,
            agent_opinions=agent_opinions,
            arbitration=arbitration,
            clarify_output=clarify_output,
            final_recommendation=final_recommendation,
        )

    def list_agents(self) -> list[dict]:
        roster = [self.pharmacist, self.attending, self.allergy, self.pharmacy, self.specialist, self.chief, self.coordinator]
        return [{"agent_id": a.agent_id, "agent_name": a.agent_name, "role": a.role} for a in roster]
