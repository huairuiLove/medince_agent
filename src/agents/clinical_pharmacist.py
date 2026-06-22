from __future__ import annotations

from src.agents.base import LLMAgent
from src.llm.client import LLMClient
from src.prompts import PHARMACIST_SYSTEM_PROMPT


class ClinicalPharmacistAgent(LLMAgent):
    agent_id = "clinical_pharmacist"
    agent_name = "临床药师"
    role = "药物相互作用、剂量、重复用药审查"
    system_prompt = PHARMACIST_SYSTEM_PROMPT

    def __init__(self, llm: LLMClient, system_prompt: str | None = None) -> None:
        super().__init__(llm, system_prompt=system_prompt)
