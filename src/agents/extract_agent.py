from __future__ import annotations

from src.llm.client import LLMClient
from src.prompts import EXTRACT_SYSTEM_PROMPT
from src.schemas import ExtractionOutput
from src.utils import coerce_llm_str_list, extract_json_payload

try:
    from src.safety_models.med7_extractor import get_med7_extractor
except ImportError:  # pragma: no cover
    get_med7_extractor = None  # type: ignore[assignment,misc]


def _normalize_extraction_payload(parsed: dict) -> dict:
    normalized = dict(parsed)
    if normalized.get("pregnancy_status") is None:
        normalized["pregnancy_status"] = "unknown"
    if normalized.get("gender") is None:
        normalized["gender"] = "unknown"
    for key in (
        "allergies",
        "symptoms_or_complaints",
        "diagnoses",
        "current_medications",
        "missing_fields",
    ):
        normalized[key] = coerce_llm_str_list(normalized.get(key))
    age = normalized.get("age")
    if isinstance(age, str) and age.strip().isdigit():
        normalized["age"] = int(age.strip())
    return normalized


class ExtractAgent:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def extract(self, text: str) -> tuple[str, ExtractionOutput | None]:
        raw = self.llm.chat(EXTRACT_SYSTEM_PROMPT, text)
        parsed = extract_json_payload(raw)
        if isinstance(parsed, dict):
            parsed = _normalize_extraction_payload(parsed)
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
