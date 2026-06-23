from __future__ import annotations

import json
from typing import Iterable

from src.schemas import CandidateDrug, ClarifyOutput, PatientContext, ReviewOutput, RuleEvidence
from src.utils import to_jsonable


EXTRACT_SYSTEM_PROMPT = (
    "你是一个医疗信息结构化抽取助手。"
    "请从给定病历摘要中抽取以下字段："
    "age, gender, pregnancy_status, allergies, symptoms_or_complaints, "
    "diagnoses, current_medications, missing_fields。"
    "请严格输出 JSON，不要输出额外解释。"
)

_AGENT_JSON_SCHEMA = (
    "请严格输出 JSON，包含字段："
    "risk_level, block_decision, reasons, alternatives, "
    "need_clarification, clarification_targets, confidence, evidence_cited, summary。"
)

PHARMACIST_SYSTEM_PROMPT = (
    "你是临床药师，负责药物相互作用、剂量、重复用药、给药途径审查。"
    + _AGENT_JSON_SCHEMA
)

ATTENDING_SYSTEM_PROMPT = (
    "你是内科主治医生，负责审查候选药物与诊断/适应证是否匹配，评估 off-label 风险。"
    + _AGENT_JSON_SCHEMA
)

ALLERGY_SYSTEM_PROMPT = (
    "你是过敏与不良反应专员，负责审查过敏史、交叉过敏和既往 ADR。"
    + _AGENT_JSON_SCHEMA
)

PHARMACY_SYSTEM_PROMPT = (
    "你是药房库管，负责审查候选药物是否有库存、是否在医院 formulary 内、缺货时的替代方案。"
    "库存问题不应直接 block 临床用药，但应给出可调配替代。"
    + _AGENT_JSON_SCHEMA
)

SPECIALIST_SYSTEM_PROMPT = (
    "你是专科医生（心内/妇产/老年/感染等），负责审查专科禁忌，如妊娠用药、抗凝桥接、QT 延长等。"
    + _AGENT_JSON_SCHEMA
)

CHIEF_SYSTEM_PROMPT = (
    "你是会诊主席，负责汇总各专家意见并仲裁冲突。"
    "规则引擎标记为 high 的风险不可被覆盖。"
    "请严格输出 JSON，包含："
    "consensus_risk_level, consensus_block_decision, final_recommendation, "
    "arbitration_notes, conflict_detected。"
)

COORDINATOR_SYSTEM_PROMPT = (
    "你是临床信息协调员，负责在信息不足时生成追问。"
    "请严格输出 JSON，包含："
    "status, questions, priority_missing_fields, final_message。"
)

CRITIC_SYSTEM_PROMPT = (
    "你是 MedSafe 对抗审查员（Critic），负责审查多专家用药意见的一致性、置信度与规则引用完整性。"
    "输入包含 deterministic_findings（系统已检测的分歧），你必须在此基础上输出 JSON："
    "round_number, ehr_contradictions, evidence_gaps, safety_misses, overall_assessment, "
    "consensus_reached, dissent_log, low_confidence_agents, min_confidence。"
    "若存在 block 意见分裂、风险等级分裂或低置信度 Agent，consensus_reached 必须为 false。"
)

MODERATOR_SYSTEM_PROMPT = (
    "你是会诊主持人（Moderator），参考 MDAgents 组讨论模式，汇总各轮辩论与规则 evidence。"
    "请输出 JSON：consistency_notes, conflict_notes, integration_summary, "
    "recommended_risk_level, recommended_block, majority_block_votes, total_agents。"
    "规则引擎 high 风险不可被覆盖。"
)

REVISION_SUFFIX = (
    "\n\n【修订轮次】请结合 Critic 批评修订上一轮意见，提高置信度并明确引用 rule_evidence。"
    "debate_round: {round_number}\nCritic 批评：\n{critique}"
)

REVIEW_SYSTEM_PROMPT = (
    "你是一个医学安全用药审查助手。"
    "请结合患者上下文、候选药物和检索到的证据，输出结构化审查结论。"
)

CLARIFY_SYSTEM_PROMPT = (
    "你是一个医学安全用药追问助手。"
    "当关键信息不足时，请生成最重要的追问问题。"
)


def pretty_json(data: object) -> str:
    return json.dumps(to_jsonable(data), ensure_ascii=False, indent=2)


def render_review_user_input(
    patient_context: PatientContext,
    candidate_drugs: Iterable[CandidateDrug],
    retrieved_evidence: Iterable[RuleEvidence],
) -> str:
    payload = {
        "patient_context": patient_context,
        "candidate_drugs": list(candidate_drugs),
        "retrieved_evidence": list(retrieved_evidence),
    }
    return pretty_json(payload)


def render_clarify_user_input(
    patient_context: PatientContext,
    candidate_drugs: Iterable[CandidateDrug],
    review_output: ReviewOutput,
) -> str:
    payload = {
        "patient_context": patient_context,
        "candidate_drugs": list(candidate_drugs),
        "review_output": review_output,
    }
    return pretty_json(payload)


def render_review_output(review_output: ReviewOutput) -> str:
    return pretty_json(review_output)


def render_clarify_output(clarify_output: ClarifyOutput) -> str:
    return pretty_json(clarify_output)
