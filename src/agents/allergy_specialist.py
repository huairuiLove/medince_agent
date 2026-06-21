from __future__ import annotations

from src.agents.base import LLMAgent
from src.llm.client import LLMClient
from src.prompts import ALLERGY_SYSTEM_PROMPT


class AllergySpecialistAgent(LLMAgent):
    agent_id = "allergy_specialist"
    agent_name = "过敏专员"
    role = "过敏史与交叉过敏审查"
    system_prompt = ALLERGY_SYSTEM_PROMPT

    def __init__(self, llm: LLMClient) -> None:
        super().__init__(llm)
