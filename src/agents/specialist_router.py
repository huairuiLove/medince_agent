from __future__ import annotations

from src.agents.base import LLMAgent
from src.agents.registry import get_agent_registry
from src.llm.client import LLMClient
from src.prompts import SPECIALIST_SYSTEM_PROMPT
from src.schemas import CandidateDrug, PatientContext


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
