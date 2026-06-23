"""Role-scoped rule evidence filters and deterministic opinion builders."""
from __future__ import annotations

from collections.abc import Callable

from src.schemas import AgentOpinion, CandidateDrug, PatientContext, RuleEvidence

PHARMACIST_CATEGORIES = frozenset({"drug_interaction", "duplicate_ingredient"})
ALLERGY_CATEGORIES = frozenset({"allergy_contraindication", "adr", "adr_history"})
ATTENDING_CATEGORIES = frozenset({"clinical_scenario"})
SPECIALIST_CATEGORIES = frozenset({"special_population", "clinical_scenario"})
DEPT_CORE_EXCLUDED = frozenset(
    {"drug_interaction", "duplicate_ingredient", "allergy_contraindication", "adr", "adr_history"}
)

_RISK_ORDER = {"high": 4, "medium": 3, "low": 2, "unknown": 1, "none": 0}


def filter_pharmacist_evidence(rule_evidence: list[RuleEvidence]) -> list[RuleEvidence]:
    return [
        item
        for item in rule_evidence
        if item.category in PHARMACIST_CATEGORIES or item.rule_id.startswith("ddi_")
    ]


def filter_attending_evidence(rule_evidence: list[RuleEvidence]) -> list[RuleEvidence]:
    return [item for item in rule_evidence if item.category in ATTENDING_CATEGORIES]


def filter_specialist_evidence(rule_evidence: list[RuleEvidence]) -> list[RuleEvidence]:
    return [item for item in rule_evidence if item.category in SPECIALIST_CATEGORIES]


def filter_department_evidence(
    rule_evidence: list[RuleEvidence],
    priority_categories: list[str] | None = None,
) -> list[RuleEvidence]:
    allowed = set(priority_categories or []) | {"clinical_scenario", "special_population"}
    allowed -= DEPT_CORE_EXCLUDED
    allowed.discard("drug_interaction")
    allowed.discard("duplicate_ingredient")
    return [item for item in rule_evidence if item.category in allowed]


def opinion_from_evidence(
    *,
    agent_id: str,
    agent_name: str,
    role: str,
    evidence: list[RuleEvidence],
    evidence_prefix: str,
    debate_round: int = 1,
    block_on_high: bool = True,
) -> AgentOpinion:
    top = max(evidence, key=lambda item: _RISK_ORDER.get(item.risk_level, 0))
    block = block_on_high and any(item.risk_level == "high" for item in evidence)
    reasons = [item.summary for item in evidence if item.summary]
    alternatives: list[str] = []
    clarification_targets: list[str] = []
    for item in evidence:
        alternatives.extend(item.alternatives)
        clarification_targets.extend(item.clarification_fields)

    return AgentOpinion(
        agent_id=agent_id,
        agent_name=agent_name,
        role=role,
        risk_level=top.risk_level,
        block_decision=block,
        reasons=reasons,
        alternatives=list(dict.fromkeys(alternatives)),
        need_clarification=bool(clarification_targets),
        clarification_targets=list(dict.fromkeys(clarification_targets)),
        confidence=0.95,
        evidence_cited=[f"{evidence_prefix}:{item.rule_id}" for item in evidence],
        summary=top.summary or "规则库命中需关注项，请结合临床上下文复核。",
        debate_round=debate_round,
    )


def strip_foreign_evidence_citations(
    opinion: AgentOpinion,
    allowed_rule_ids: set[str],
    *,
    evidence_prefix: str,
    foreign_markers: tuple[str, ...],
) -> AgentOpinion:
    opinion.evidence_cited = [
        item
        for item in opinion.evidence_cited
        if item.startswith(f"{evidence_prefix}:")
        or any(rule_id in item for rule_id in allowed_rule_ids)
    ]
    blob = " ".join(opinion.reasons + [opinion.summary] + opinion.evidence_cited).lower()
    if opinion.block_decision and any(marker in blob for marker in foreign_markers):
        opinion.block_decision = False
        if not allowed_rule_ids:
            opinion.risk_level = "low"
        opinion.reasons = ["（已忽略超出本角色职责的理由）", *opinion.reasons]
    return opinion


def scoped_user_payload(
    patient_context: PatientContext,
    candidate_drugs: list[CandidateDrug],
    scoped_evidence: list[RuleEvidence],
    *,
    instruction: str,
    extra: dict | None = None,
) -> dict:
    payload = {
        "patient_context": patient_context.model_dump(),
        "candidate_drugs": [d.model_dump() for d in candidate_drugs],
        "rule_evidence": [e.model_dump() for e in scoped_evidence],
        "instruction": instruction,
    }
    if extra:
        payload.update(extra)
    return payload


RoleReviewFn = Callable[
    [PatientContext, list[CandidateDrug], list[RuleEvidence], int],
    AgentOpinion,
]
