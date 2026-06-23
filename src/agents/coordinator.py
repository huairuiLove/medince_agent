from __future__ import annotations

from src.llm.client import LLMClient
from src.prompts import COORDINATOR_SYSTEM_PROMPT, pretty_json
from src.schemas import (
    CandidateDrug,
    ClarifyOutput,
    ClarifyQuestion,
    ClarifyStatus,
    PatientContext,
    ReviewOutput,
)


_STATUS_ALIASES: dict[str, ClarifyStatus] = {
    "need_user_input": "need_user_input",
    "need_clarification": "need_user_input",
    "need_more_info": "need_user_input",
    "conservative_fallback": "conservative_fallback",
    "conservative": "conservative_fallback",
    "fallback": "conservative_fallback",
    "complete": "complete",
    "done": "complete",
}


def _normalize_clarify_status(value: object, default: ClarifyStatus = "need_user_input") -> ClarifyStatus:
    if not isinstance(value, str):
        return default
    key = value.strip().lower()
    return _STATUS_ALIASES.get(key, default)


class CoordinatorAgent:
    """信息协调员 — LLM 生成追问，规则引擎兜底。"""

    agent_id = "coordinator"
    agent_name = "信息协调员"
    role = "追问生成与信息补全"

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def clarify(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        review_output: ReviewOutput,
        unable_to_answer: bool = False,
    ) -> ClarifyOutput:
        payload = {
            "patient_context": patient_context.model_dump(),
            "candidate_drugs": [d.model_dump() for d in candidate_drugs],
            "review_output": review_output.model_dump(),
            "unable_to_answer": unable_to_answer,
        }
        data = self.llm.chat_json(COORDINATOR_SYSTEM_PROMPT, pretty_json(payload))
        if not data:
            from src.clarify_engine import ClarifyEngine
            return ClarifyEngine().clarify(
                patient_context, candidate_drugs, review_output, unable_to_answer=unable_to_answer
            )

        questions: list[ClarifyQuestion] = []
        for q in data.get("questions", []):
            if isinstance(q, str) and q.strip():
                questions.append(
                    ClarifyQuestion(field="", question=q.strip(), reason="", priority="medium")
                )
            elif isinstance(q, dict):
                questions.append(
                    ClarifyQuestion(
                        field=str(q.get("field", "")),
                        question=str(q.get("question", "")),
                        reason=str(q.get("reason", "")),
                        priority=q.get("priority", "medium"),
                    )
                )

        return ClarifyOutput(
            status=_normalize_clarify_status(data.get("status")),
            questions=questions,
            priority_missing_fields=list(data.get("priority_missing_fields", [])),
            conservative_advice=None,
            final_message=str(data.get("final_message", "")),
        )
