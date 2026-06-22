from __future__ import annotations

from src.agents.base import LLMAgent
from src.llm.client import LLMClient
from src.prompts import ATTENDING_SYSTEM_PROMPT


class InternalMedicineAgent(LLMAgent):
    agent_id = "internal_medicine"
    agent_name = "内科主治"
    role = "适应证与疾病-药物匹配审查"
    system_prompt = ATTENDING_SYSTEM_PROMPT

    def __init__(self, llm: LLMClient, system_prompt: str | None = None) -> None:
        super().__init__(llm, system_prompt=system_prompt)
