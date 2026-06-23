"""Department-weighted rule evidence sorting — boost same-dept rules, never hide others."""

from __future__ import annotations

from typing import Any

from src.schemas import RuleEvidence

DEPT_BOOST = 1.5
GENERIC_BOOST = 1.0
OTHER_DEPT_BOOST = 0.8
DEPT_FOCUS_PREFIX = "[本科室重点] "

RISK_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3, "unknown": 4}


class DepartmentRulePrioritizer:
    """Apply department-weighted sorting to rule evidence without filtering."""

    def __init__(
        self,
        department: str | None = None,
        priority_categories: list[str] | None = None,
    ) -> None:
        self.department = (department or "").strip().lower()
        self.priority_categories = {c.lower() for c in (priority_categories or [])}

    def _rule_department(self, rule_id: str, rule_lookup: dict[str, dict[str, Any]]) -> str | None:
        rule = rule_lookup.get(rule_id)
        if not rule:
            return None
        dept = rule.get("department")
        return str(dept).strip().lower() if dept else None

    def priority_boost(
        self,
        evidence: RuleEvidence,
        rule_lookup: dict[str, dict[str, Any]],
    ) -> float:
        rule_dept = self._rule_department(evidence.rule_id, rule_lookup)
        if not self.department:
            boost = GENERIC_BOOST
        elif rule_dept == self.department:
            boost = DEPT_BOOST
        elif rule_dept is None:
            boost = GENERIC_BOOST
        else:
            boost = OTHER_DEPT_BOOST

        if self.priority_categories and evidence.category.lower() in self.priority_categories:
            boost += 0.1
        return boost

    def annotate_summary(self, evidence: RuleEvidence, rule_lookup: dict[str, dict[str, Any]]) -> str:
        rule_dept = self._rule_department(evidence.rule_id, rule_lookup)
        if self.department and rule_dept == self.department:
            if not evidence.summary.startswith(DEPT_FOCUS_PREFIX):
                return f"{DEPT_FOCUS_PREFIX}{evidence.summary}"
        return evidence.summary

    def sort_key(
        self,
        evidence: RuleEvidence,
        rule_lookup: dict[str, dict[str, Any]],
    ) -> tuple[float, int]:
        boost = self.priority_boost(evidence, rule_lookup)
        risk = RISK_ORDER.get(evidence.risk_level, 0)
        return (-boost, -risk)

    def apply(
        self,
        evidence: list[RuleEvidence],
        rule_lookup: dict[str, dict[str, Any]],
    ) -> list[RuleEvidence]:
        if not evidence:
            return evidence

        annotated: list[RuleEvidence] = []
        for item in evidence:
            summary = self.annotate_summary(item, rule_lookup)
            if summary != item.summary:
                annotated.append(item.model_copy(update={"summary": summary}))
            else:
                annotated.append(item)

        return sorted(
            annotated,
            key=lambda e: self.sort_key(e, rule_lookup),
        )
