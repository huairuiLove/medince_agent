from __future__ import annotations

from src.llm.client import LLMClient
from src.prompts import COORDINATOR_SYSTEM_PROMPT, pretty_json
from src.schemas import (
    CandidateDrug,
    ClarifyOutput,
    ClarifyQuestion,
    ConservativeAdvice,
    PatientContext,
    ReviewOutput,
)


class CoordinatorAgent:
    """信息协调员 — LLM 生成追问，规则引擎兜底。"""

    agent_id = "coordinator"
    agent_name = "信息协调员"
    role = "追问生成与保守降级"

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

        conservative = None
        if data.get("conservative_advice"):
            ca = data["conservative_advice"]
            conservative = ConservativeAdvice(
                summary=ca.get("summary", ""),
                actions=list(ca.get("actions", [])),
                disclaimer=ca.get("disclaimer", ""),
            )

        questions = [
            ClarifyQuestion(
                field=q.get("field", ""),
                question=q.get("question", ""),
                reason=q.get("reason", ""),
                priority=q.get("priority", "medium"),
            )
            for q in data.get("questions", [])
        ]

        return ClarifyOutput(
            status=data.get("status", "need_user_input"),
            questions=questions,
            priority_missing_fields=list(data.get("priority_missing_fields", [])),
            conservative_advice=conservative,
            final_message=data.get("final_message", ""),
        )
