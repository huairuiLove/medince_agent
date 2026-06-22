from __future__ import annotations

from src.llm.client import LLMClient
from src.prompts import EXTRACT_SYSTEM_PROMPT
from src.schemas import ExtractionOutput
from src.utils import extract_json_payload

try:
    from src.safety_models.med7_extractor import get_med7_extractor
except ImportError:  # pragma: no cover
    get_med7_extractor = None  # type: ignore[assignment,misc]


class ExtractAgent:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def extract(self, text: str) -> tuple[str, ExtractionOutput | None]:
        raw = self.llm.chat(EXTRACT_SYSTEM_PROMPT, text)
        parsed = extract_json_payload(raw)
        if isinstance(parsed, dict):
            if parsed.get("pregnancy_status") is None:
                parsed["pregnancy_status"] = "unknown"
            if parsed.get("allergies") is None:
                parsed["allergies"] = []
            if parsed.get("gender") is None:
                parsed["gender"] = "unknown"
        extraction = ExtractionOutput.model_validate(parsed) if parsed else None
        extraction = self._merge_med7(text, extraction)
        return raw, extraction

    def _merge_med7(self, text: str, extraction: ExtractionOutput | None) -> ExtractionOutput | None:
        if get_med7_extractor is None:
            return extraction
        med7 = get_med7_extractor()
        if not med7.available and not med7._ensure_loaded():  # noqa: SLF001
            return extraction
        return med7.enrich_extraction(text, extraction)
