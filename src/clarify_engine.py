from __future__ import annotations

from src.schemas import CandidateDrug, ClarifyOutput, ClarifyQuestion, ConservativeAdvice, PatientContext, ReviewOutput
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

    def _build_conservative_advice(
        self,
        review_output: ReviewOutput,
        candidate_drugs: list[CandidateDrug],
    ) -> ConservativeAdvice:
        drug_names = [drug.name for drug in candidate_drugs if drug.name]
        if review_output.risk_level == "high":
            summary = "由于已命中高风险规则，当前不建议直接使用候选药物方案。"
        else:
            summary = "由于关键信息仍然缺失，当前建议采用保守策略，暂缓直接给出积极用药建议。"

        actions = []
        if drug_names:
            actions.append(f"在未补全信息前，暂缓启动或追加以下药物：{', '.join(drug_names)}。")
        if review_output.alternative_suggestions:
            actions.append(f"可优先考虑更安全的替代思路：{'；'.join(review_output.alternative_suggestions[:3])}。")
        actions.append("建议补充过敏史、妊娠状态、年龄和当前全部用药后重新审查。")

        disclaimer = "本结果为最小规则库驱动的保守审查结论，不能替代执业医师或药师的正式决策。"
        return ConservativeAdvice(summary=summary, actions=actions, disclaimer=disclaimer)

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
            conservative_advice = self._build_conservative_advice(review_output, candidate_drugs)
            return ClarifyOutput(
                status="conservative_fallback",
                questions=[],
                priority_missing_fields=remaining_fields,
                conservative_advice=conservative_advice,
                final_message="由于无法补充关键信息，系统已切换为保守输出。建议暂缓高风险或信息依赖较强的方案。",
            )

        if questions:
            return ClarifyOutput(
                status="need_user_input",
                questions=questions,
                priority_missing_fields=remaining_fields,
                conservative_advice=None,
                final_message="当前仍需补充关键信息后才能继续完成更稳妥的安全审查。",
            )

        return ClarifyOutput(
            status="complete",
            questions=[],
            priority_missing_fields=[],
            conservative_advice=None,
            final_message="当前没有必须继续追问的关键字段，可进入人工复核或下一步处置。",
        )
