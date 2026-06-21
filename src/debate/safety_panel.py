"""Deterministic safety panel — parallel rule + DDI check (ClinicalPilot safety_panel pattern)."""
from __future__ import annotations

from src.review_engine import ReviewEngine
from src.schemas import CandidateDrug, PatientContext, ReviewOutput, SafetyFlag, SafetyPanelResult


class SafetyPanel:
    """Run rule engine as an independent safety audit parallel to LLM debate."""

    def __init__(self, review_engine: ReviewEngine | None = None) -> None:
        self.review_engine = review_engine or ReviewEngine()

    def run(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
    ) -> SafetyPanelResult:
        output: ReviewOutput = self.review_engine.review(patient_context, candidate_drugs)
        flags: list[SafetyFlag] = []
        for ev in output.evidence:
            flags.append(
                SafetyFlag(
                    severity=ev.risk_level if ev.risk_level in {"high", "medium", "low"} else "medium",
                    category=ev.category,
                    description=ev.summary,
                    recommendation=ev.recommendation or "请人工复核或调整方案。",
                    rule_id=ev.rule_id,
                    implicated_drugs=ev.implicated_drugs,
                )
            )

        ddi_hits = [f for f in flags if f.category == "drug_interaction"]
        passed = not output.block_decision and output.risk_level not in {"high", "unknown"}

        return SafetyPanelResult(
            passed=passed,
            risk_level=output.risk_level,
            block_recommended=output.block_decision,
            flags=flags,
            ddi_hits=ddi_hits,
            summary=output.final_recommendation or self._summarize(flags, passed),
        )

    @staticmethod
    def _summarize(flags: list[SafetyFlag], passed: bool) -> str:
        if not flags:
            return "Safety Panel：规则库未命中额外风险。"
        if passed:
            return f"Safety Panel：命中 {len(flags)} 条提示，未达阻断阈值。"
        return f"Safety Panel：命中 {len(flags)} 条风险，建议阻断或人工复核。"
