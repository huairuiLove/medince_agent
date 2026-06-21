from __future__ import annotations

from src.agents.base import LLMAgent
from src.llm.client import LLMClient
from src.prompts import EXTRACT_SYSTEM_PROMPT
from src.schemas import ExtractionOutput
from src.utils import extract_json_payload


class ExtractAgent:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def extract(self, text: str) -> tuple[str, ExtractionOutput | None]:
        raw = self.llm.chat(EXTRACT_SYSTEM_PROMPT, text)
        parsed = extract_json_payload(raw)
        if parsed is None:
            return raw, None
        return raw, ExtractionOutput.model_validate(parsed)
