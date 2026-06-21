from __future__ import annotations

from src.agents.base import LLMAgent
from src.llm.client import LLMClient
from src.prompts import SPECIALIST_SYSTEM_PROMPT
from src.schemas import CandidateDrug, PatientContext


class SpecialistAgent(LLMAgent):
    agent_id = "specialist"
    agent_name = "专科医生"
    role = "专科禁忌审查（妊娠/抗凝/感染等）"
    system_prompt = SPECIALIST_SYSTEM_PROMPT

    def __init__(self, llm: LLMClient) -> None:
        super().__init__(llm)

    @staticmethod
    def should_activate(patient_context: PatientContext, candidate_drugs: list[CandidateDrug]) -> bool:
        drug_names = " ".join(d.name.lower() for d in candidate_drugs)
        if any(k in drug_names for k in ("warfarin", "heparin", "enoxaparin", "lisinopril", "losartan")):
            return True
        if str(patient_context.gender).upper() in {"F", "FEMALE"}:
            if patient_context.age is None or 12 <= patient_context.age <= 55:
                return True
        if patient_context.age and patient_context.age >= 65:
            return True
        return False
