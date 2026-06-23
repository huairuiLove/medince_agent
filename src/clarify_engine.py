from __future__ import annotations

from src.schemas import CandidateDrug, ClarifyOutput, ClarifyQuestion, PatientContext, ReviewOutput
from src.utils import dedupe_preserve_order


QUESTION_TEMPLATES = {
    "allergies": ("请问患者是否存在药物过敏史？如果有，请明确过敏药物名称和反应。", "过敏信息缺失会影响是否可以安全使用候选药物。"),
    "pregnancy_status": ("请问患者当前是否怀孕、备孕或哺乳？", "部分候选药物对妊娠或哺乳人群存在禁忌或限制。"),
    "current_medications": ("请补充患者目前正在服用的全部药物、保健品或中成药。", "当前用药不完整会影响相互作用审查。"),
    "age": ("请问患者年龄是多少？", "年龄会影响特殊人群禁忌与剂量安全性判断。"),
    "gender": ("请问患者性别是？", "性别信息会影响妊娠相关风险判断。"),
    "diagnoses": ("请补充患者当前主要诊断或既往重要病史。", "诊断信息会影响用药适应证和禁忌判断。"),
    "chief_complaint": ("请再描述一下这次最主要的不适或主诉。", "主诉信息有助于判断候选药物是否适合当前场景。"),
}

QUESTION_PRIORITY = {
    "pregnancy_status": "high",
    "allergies": "high",
    "current_medications": "high",
    "age": "high",
    "diagnoses": "medium",
    "gender": "medium",
    "chief_complaint": "low",
}


class ClarifyEngine:
    def _build_questions(
        self,
        patient_context: PatientContext,
        review_output: ReviewOutput,
        user_answers: dict[str, str],
    ) -> list[ClarifyQuestion]:
        answered_fields = {field for field, value in user_answers.items() if str(value).strip()}
        targets = dedupe_preserve_order(review_output.clarification_targets + patient_context.missing_fields)
        questions: list[ClarifyQuestion] = []

        for field in targets:
            if field in answered_fields:
                continue
            question_text, reason = QUESTION_TEMPLATES.get(
                field,
                (f"请补充字段 {field} 的相关信息。", "该字段缺失会影响当前用药风险判断。"),
            )
            questions.append(
                ClarifyQuestion(
                    field=field,
                    question=question_text,
                    reason=reason,
                    priority=QUESTION_PRIORITY.get(field, "medium"),
                )
            )

        questions.sort(key=lambda item: {"high": 0, "medium": 1, "low": 2}[item.priority])
        return questions[:3]

    def clarify(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        review_output: ReviewOutput,
        user_answers: dict[str, str] | None = None,
        unable_to_answer: bool = False,
    ) -> ClarifyOutput:
        user_answers = user_answers or {}
        questions = self._build_questions(patient_context, review_output, user_answers)
        remaining_fields = [question.field for question in questions]

        if unable_to_answer:
            return ClarifyOutput(
                status="complete",
                questions=[],
                priority_missing_fields=remaining_fields,
                conservative_advice=None,
                final_message="关键信息仍未补全，建议人工复核后再决定用药方案。",
            )

        if questions:
            return ClarifyOutput(
                status="need_user_input",
                questions=questions,
                priority_missing_fields=remaining_fields,
                conservative_advice=None,
                final_message="请补充关键信息后继续审查。",
            )

        return ClarifyOutput(
            status="complete",
            questions=[],
            priority_missing_fields=[],
            conservative_advice=None,
            final_message="当前没有必须继续追问的关键字段，可进入人工复核或下一步处置。",
        )
