#!/usr/bin/env python3
"""Run Stage 9/11 benchmark evaluation against benchmark cases."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.department.priority import DEPT_FOCUS_PREFIX, normalize_department
from src.drug_catalog.review_facade import CpoeReviewFacade
from src.knowledge_base import SafetyKnowledgeBase
from src.llm.client import is_llm_configured
from src.llm.errors import LLMNotConfiguredError
from src.orchestrator import MultiAgentOrchestrator
from src.review_engine import ReviewEngine
from src.schemas import (
    CandidateDrug,
    CpoeMedicationOrder,
    CpoeMedicationReviewRequest,
    CpoePatientSnapshot,
    DrugItem,
    PatientContext,
    RuleEvidence,
)
from src.utils import load_json, save_json

DEFAULT_KB = PROJECT_ROOT / "datasets" / "knowledge" / "hospital_production_v5.json"
CASES_DIR = PROJECT_ROOT / "datasets" / "benchmark" / "cases"
REPORTS_DIR = PROJECT_ROOT / "datasets" / "benchmark" / "reports"

KB_ALIASES: dict[str, Path] = {
    "expanded_mined_v1": PROJECT_ROOT / "datasets" / "knowledge" / "expanded_drug_safety_rules.json",
    "internal_medicine_full": PROJECT_ROOT / "datasets" / "knowledge" / "hospital_production_v4.json",
    "hospital_production_v4": PROJECT_ROOT / "datasets" / "knowledge" / "hospital_production_v4.json",
    "hospital_production_v5": PROJECT_ROOT / "datasets" / "knowledge" / "hospital_production_v5.json",
    "minimal": PROJECT_ROOT / "datasets" / "knowledge" / "minimal_drug_safety_rules.json",
}

ALL_DEPARTMENTS = [
    "cardiology",
    "respiratory",
    "neurology",
    "endocrinology",
    "gastroenterology",
    "nephrology",
    "hematology",
    "rheumatology",
    "infectious",
    "psychiatry",
    "geriatrics",
    "icu",
    "obgyn",
    "neurosurgery",
    "radiology",
    "oncology",
    "emergency",
    "general_internal",
    "pediatrics",
    "orthopedic",
    "urology",
    "anesthesiology",
    "dermatology",
    "ophthalmology",
    "ent",
    "rehabilitation",
]


def _resolve_kb_path(name_or_path: str) -> Path:
    if name_or_path in KB_ALIASES:
        return KB_ALIASES[name_or_path]
    path = Path(name_or_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _load_cases(cases_dir: Path, department: str) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for path in sorted(cases_dir.glob("*.json")):
        case = load_json(path)
        if department != "all" and case.get("department") != department:
            continue
        case["_path"] = str(path)
        cases.append(case)
    return cases


def _output_to_actual(output, candidates: list[CandidateDrug]) -> dict[str, Any]:
    candidate_names = {normalize_name(item.name) for item in candidates}
    candidate_names.update(normalize_name(item.ingredient) for item in candidates if item.ingredient)

    fired_rules = {item.rule_id for item in output.evidence}
    attributed = 0
    attribution_total = 0
    for alert in output.evidence:
        if alert.rule_id.startswith("ddi_model_"):
            continue
        attribution_total += 1
        implicated = {normalize_name(name) for name in alert.implicated_drugs}
        if implicated & candidate_names:
            attributed += 1

    return {
        "risk_level": output.risk_level,
        "block_decision": output.block_decision,
        "fired_rule_ids": sorted(fired_rules),
        "evidence_count": len(output.evidence),
        "alert_attribution": (attributed / attribution_total) if attribution_total else 1.0,
    }


def _resolve_department(case: dict[str, Any]) -> str:
    dept = case.get("department") or case.get("request", {}).get("patient_context", {}).get("department", "")
    return normalize_department(str(dept))


def _run_rule_review(case: dict[str, Any], engine: ReviewEngine) -> dict[str, Any]:
    request = case["request"]
    patient_raw = dict(request["patient_context"])
    dept = _resolve_department(case)
    if dept:
        patient_raw["department"] = dept
    patient = PatientContext.model_validate(patient_raw)
    candidates = [CandidateDrug.model_validate(item) for item in request.get("candidate_drugs", [])]
    output = engine.review(patient, candidates, department=dept or None)
    actual = _output_to_actual(output, candidates)
    actual["evidence"] = output.evidence
    actual["department"] = dept
    return actual


def _case_to_cpoe_request(case: dict[str, Any]) -> CpoeMedicationReviewRequest:
    request = case["request"]
    patient_ctx = request["patient_context"]
    patient = CpoePatientSnapshot(
        patient_id=str(patient_ctx.get("subject_id", case["case_id"])),
        gender=patient_ctx.get("gender", "unknown"),
        age=patient_ctx.get("age"),
        weight_kg=patient_ctx.get("weight_kg"),
        egfr=patient_ctx.get("egfr"),
        allergies=list(patient_ctx.get("allergies", [])),
        pregnancy_status=patient_ctx.get("pregnancy_status", "unknown"),
        lactation_status=patient_ctx.get("lactation_status", "unknown"),
    )
    existing = [DrugItem.model_validate(item) for item in patient_ctx.get("current_medications", [])]
    orders = [
        CpoeMedicationOrder(
            order_id=f"ORD-{index + 1}",
            display_name=item.get("name") or item.get("ingredient", ""),
            ingredient=item.get("ingredient") or item.get("name", ""),
            dose=item.get("dose", ""),
            route=item.get("route", ""),
            frequency=item.get("frequency", ""),
        )
        for index, item in enumerate(request.get("candidate_drugs", []))
    ]
    return CpoeMedicationReviewRequest(
        encounter_id=case["case_id"],
        patient=patient,
        orders=orders,
        existing_medications=existing,
        department=_resolve_department(case),
    )


def _run_cpoe_review(case: dict[str, Any], kb_path: Path) -> dict[str, Any]:
    kb = SafetyKnowledgeBase(kb_path)
    facade = CpoeReviewFacade(review_engine=ReviewEngine(kb=kb))
    cpoe_request = _case_to_cpoe_request(case)
    response = facade.review(cpoe_request)
    if response.review_output is None:
        raise RuntimeError(f"CPOE review returned no review_output for {case['case_id']}")
    candidates = [CandidateDrug.model_validate(item) for item in case["request"].get("candidate_drugs", [])]
    actual = _output_to_actual(response.review_output, candidates)
    actual["evidence"] = response.review_output.evidence
    actual["department"] = _resolve_department(case)
    clinical_rule_ids = {
        alert.rule_id
        for alert in response.alerts
        if alert.category not in {"formulary", "inventory", "terminology", "high_alert"}
    }
    actual["fired_rule_ids"] = sorted(set(actual["fired_rule_ids"]) | clinical_rule_ids)
    return actual


def _run_full_pipeline_review(case: dict[str, Any], kb_path: Path) -> dict[str, Any]:
    if not is_llm_configured():
        raise LLMNotConfiguredError(
            "full-pipeline benchmark requires configured LLM (llm.provider + api_key in config.yaml)"
        )
    request = case["request"]
    patient_raw = dict(request["patient_context"])
    dept = _resolve_department(case)
    if dept:
        patient_raw["department"] = dept
    patient = PatientContext.model_validate(patient_raw)
    candidates = [CandidateDrug.model_validate(item) for item in request.get("candidate_drugs", [])]
    engine = ReviewEngine(kb=SafetyKnowledgeBase(kb_path))
    orchestrator = MultiAgentOrchestrator()
    orchestrator.review_engine = engine
    multi = orchestrator.run(patient, candidates, skip_clarify=True)
    actual = _output_to_actual(multi.rule_output, candidates)
    actual["evidence"] = multi.rule_output.evidence
    actual["department"] = dept
    actual["risk_level"] = multi.arbitration.consensus_risk_level
    actual["block_decision"] = multi.arbitration.consensus_block_decision
    return actual


def normalize_name(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def _dept_rule_ids(kb: SafetyKnowledgeBase, dept: str) -> set[str]:
    tag = normalize_department(dept)
    ids: set[str] = set()
    for rule in kb.get_interaction_rules():
        rule_dept = normalize_department(str(rule.get("department") or ""))
        if rule_dept and rule_dept == tag:
            rid = rule.get("rule_id")
            if rid:
                ids.add(str(rid))
    return ids


def _evaluate_department_boost(
    case: dict[str, Any],
    actual: dict[str, Any],
    kb: SafetyKnowledgeBase,
) -> dict[str, Any] | None:
    gt = case.get("ground_truth") or {}
    expected_dept = gt.get("expected_department_boost")
    if not expected_dept:
        return None

    dept = normalize_department(str(expected_dept))
    evidence: list[RuleEvidence] = actual.get("evidence") or []
    dept_rule_ids = _dept_rule_ids(kb, dept)

    required = [
        item["rule_id"]
        for item in gt.get("required_alerts", [])
        if item.get("must_fire", True) and item["rule_id"] in dept_rule_ids
    ]
    if not required:
        return None

    boosted = [
        rid for rid in required
        if any(
            ev.rule_id == rid and ev.summary.startswith(DEPT_FOCUS_PREFIX)
            for ev in evidence
        )
    ]
    ranked_ok = False
    if evidence:
        dept_positions = [
            index for index, ev in enumerate(evidence)
            if ev.rule_id in dept_rule_ids
        ]
        other_positions = [
            index for index, ev in enumerate(evidence)
            if ev.rule_id not in dept_rule_ids and ev.category == "drug_interaction"
        ]
        if dept_positions and other_positions:
            ranked_ok = min(dept_positions) < min(other_positions)
        elif dept_positions:
            ranked_ok = True

    boost_applied = len(boosted) == len(required) or (len(boosted) > 0 and ranked_ok)
    return {
        "case_id": case["case_id"],
        "expected_department_boost": dept,
        "boost_applied": boost_applied,
        "boosted_rule_ids": boosted,
        "required_dept_rules": required,
        "dept_ranked_first": ranked_ok,
    }


def _aggregate_department_boost(boost_results: list[dict[str, Any] | None]) -> dict[str, Any]:
    relevant = [item for item in boost_results if item is not None]
    if not relevant:
        return {"case_count": 0, "department_boost_accuracy": None}
    passed = sum(1 for item in relevant if item.get("boost_applied"))
    return {
        "case_count": len(relevant),
        "department_boost_passed": passed,
        "department_boost_accuracy": round(passed / len(relevant), 4),
        "failures": [item for item in relevant if not item.get("boost_applied")],
    }


def _evaluate_case(case: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    gt = case["ground_truth"]
    required = [item for item in gt.get("required_alerts", []) if item.get("must_fire", True)]
    should_not = set(gt.get("should_not_fire", []))

    tp = sum(1 for item in required if item["rule_id"] in actual["fired_rule_ids"])
    fn = len(required) - tp
    fp = len([rule_id for rule_id in actual["fired_rule_ids"] if rule_id in should_not])
    tn = len(should_not) - fp

    extra_fp = [
        rule_id
        for rule_id in actual["fired_rule_ids"]
        if rule_id not in {item["rule_id"] for item in required} and rule_id not in should_not
    ]

    if gt.get("is_negative_test"):
        evidence = actual.get("evidence") or []
        high_clinical = [
            ev for ev in evidence
            if ev.risk_level in {"high", "medium"}
            and getattr(ev, "source", "") != "ddi_bert_model"
            and not str(ev.rule_id).startswith("ddi_model_")
        ]
        clarification_only = (
            not high_clinical
            and not evidence
            and actual["risk_level"] == "unknown"
        )
        passed = (
            (not high_clinical and actual["risk_level"] in {"none", "low"})
            or clarification_only
        ) and fn == 0
    else:
        passed = not (
            fn > 0
            or fp > 0
            or actual["risk_level"] != gt.get("risk_level")
            or actual["block_decision"] != gt.get("block_decision")
        )

    return {
        "case_id": case["case_id"],
        "department": case.get("department"),
        "path": case.get("_path"),
        "tp": tp,
        "fn": fn,
        "fp": fp,
        "tn": tn,
        "required_count": len(required),
        "missing_required": [
            item["rule_id"] for item in required if item["rule_id"] not in actual["fired_rule_ids"]
        ],
        "unexpected_fired": list(extra_fp),
        "risk_level_match": actual["risk_level"] == gt.get("risk_level"),
        "block_decision_match": actual["block_decision"] == gt.get("block_decision"),
        "actual_risk_level": actual["risk_level"],
        "expected_risk_level": gt.get("risk_level"),
        "actual_block_decision": actual["block_decision"],
        "expected_block_decision": gt.get("block_decision"),
        "alert_attribution": actual["alert_attribution"],
        "passed": passed,
        "is_negative_test": bool(gt.get("is_negative_test")),
    }


def _aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    tp = sum(item["tp"] for item in results)
    fn = sum(item["fn"] for item in results)
    fp = sum(item["fp"] for item in results)
    tn = sum(item["tn"] for item in results)

    sensitivity = tp / (tp + fn) if (tp + fn) else 1.0
    specificity = tn / (tn + fp) if (tn + fp) else 1.0
    risk_accuracy = (
        sum(1 for item in results if item["risk_level_match"]) / len(results) if results else 0.0
    )

    block_tp = sum(
        1
        for item in results
        if item["actual_block_decision"] and item["expected_block_decision"]
    )
    block_fp = sum(
        1
        for item in results
        if item["actual_block_decision"] and not item["expected_block_decision"]
    )
    block_fn = sum(
        1
        for item in results
        if not item["actual_block_decision"] and item["expected_block_decision"]
    )
    block_tn = sum(
        1
        for item in results
        if not item["actual_block_decision"] and not item["expected_block_decision"]
    )
    block_precision = block_tp / (block_tp + block_fp) if (block_tp + block_fp) else 0.0
    block_recall = block_tp / (block_tp + block_fn) if (block_tp + block_fn) else 0.0
    block_f1 = (
        2 * block_precision * block_recall / (block_precision + block_recall)
        if (block_precision + block_recall)
        else 0.0
    )

    attribution = (
        sum(item["alert_attribution"] for item in results) / len(results) if results else 0.0
    )

    return {
        "case_count": len(results),
        "alert_sensitivity": round(sensitivity, 4),
        "alert_specificity": round(specificity, 4),
        "risk_level_accuracy": round(risk_accuracy, 4),
        "block_decision_precision": round(block_precision, 4),
        "block_decision_recall": round(block_recall, 4),
        "block_decision_f1": round(block_f1, 4),
        "alert_attribution": round(attribution, 4),
        "passed_cases": sum(1 for item in results if item["passed"]),
        "failed_cases": sum(1 for item in results if not item["passed"]),
    }


def _department_breakdown(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_dept: dict[str, list[dict[str, Any]]] = {}
    for item in results:
        by_dept.setdefault(item["department"] or "unknown", []).append(item)
    return {dept: _aggregate(items) for dept, items in sorted(by_dept.items())}


def run_benchmark(
    *,
    mode: str,
    department: str,
    kb_path: Path,
    cases_dir: Path,
    kb_v2_path: Path | None = None,
) -> dict[str, Any]:
    cases = _load_cases(cases_dir, department)
    if not cases:
        raise SystemExit(f"No benchmark cases found in {cases_dir} for department={department}")

    kb = SafetyKnowledgeBase(kb_path)

    if mode == "compare":
        if kb_v2_path is None:
            raise SystemExit("compare mode requires --kb-v2")
        kb_v1_engine = ReviewEngine(kb=SafetyKnowledgeBase(kb_path))
        kb_v2_engine = ReviewEngine(kb=SafetyKnowledgeBase(kb_v2_path))
        results_v1 = []
        results_v2 = []
        for case in cases:
            actual_v1 = _run_rule_review(case, kb_v1_engine)
            actual_v2 = _run_rule_review(case, kb_v2_engine)
            results_v1.append(_evaluate_case(case, actual_v1))
            results_v2.append(_evaluate_case(case, actual_v2))
        return {
            "mode": mode,
            "department": department,
            "case_count": len(cases),
            "kb_v1": str(kb_path),
            "kb_v2": str(kb_v2_path),
            "kb_v1_metrics": _aggregate(results_v1),
            "kb_v2_metrics": _aggregate(results_v2),
            "kb_v1_by_department": _department_breakdown(results_v1),
            "kb_v2_by_department": _department_breakdown(results_v2),
            "kb_v1_failures": [item for item in results_v1 if not item["passed"]],
            "kb_v2_failures": [item for item in results_v2 if not item["passed"]],
        }

    engine = ReviewEngine(kb=kb)
    case_results: list[dict[str, Any]] = []
    boost_results: list[dict[str, Any] | None] = []
    actuals: list[dict[str, Any]] = []
    for case in cases:
        if mode == "rule-only":
            actual = _run_rule_review(case, engine)
        elif mode == "cpoe":
            actual = _run_cpoe_review(case, kb_path)
        elif mode == "full-pipeline":
            actual = _run_full_pipeline_review(case, kb_path)
        else:
            raise SystemExit(f"Unsupported mode: {mode}")

        actuals.append(actual)
        boost_results.append(_evaluate_department_boost(case, actual, kb))
        case_results.append(_evaluate_case(case, actual))

    metrics = _aggregate(case_results)
    metrics["department_boost"] = _aggregate_department_boost(boost_results)
    metrics["stage11_clinical_cases"] = sum(
        1 for c in cases if c.get("case_id", "").startswith("clinical_")
    )
    metrics["stage11_negative_cases"] = sum(
        1 for c in cases if c.get("case_id", "").startswith("negative_")
    )
    failures = [item for item in case_results if not item["passed"]]
    return {
        "mode": mode,
        "department": department,
        "kb_path": str(kb_path),
        "cases_dir": str(cases_dir),
        "metrics": metrics,
        "by_department": _department_breakdown(case_results),
        "failures": failures,
        "case_results": case_results,
        "department_boost_details": [b for b in boost_results if b],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run MedSafe Stage 9 benchmark")
    parser.add_argument(
        "--mode",
        choices=["rule-only", "cpoe", "full-pipeline", "compare"],
        default="rule-only",
    )
    parser.add_argument("--dept", default="all", help="Department filter or 'all'")
    parser.add_argument("--kb", default=str(DEFAULT_KB), help="Knowledge base path or alias")
    parser.add_argument(
        "--kb-v1",
        default="expanded_mined_v1",
        help="KB v1 alias/path for compare mode",
    )
    parser.add_argument(
        "--kb-v2",
        default="hospital_production_v5",
        help="KB v2 alias/path for compare mode",
    )
    parser.add_argument("--cases-dir", type=Path, default=CASES_DIR)
    parser.add_argument("--reports-dir", type=Path, default=REPORTS_DIR)
    args = parser.parse_args()

    if args.dept != "all" and args.dept not in ALL_DEPARTMENTS:
        raise SystemExit(f"Unknown department: {args.dept}")

    reports_dir = args.reports_dir
    reports_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if args.mode == "compare":
        report = run_benchmark(
            mode=args.mode,
            department=args.dept,
            kb_path=_resolve_kb_path(args.kb_v1),
            cases_dir=args.cases_dir,
            kb_v2_path=_resolve_kb_path(args.kb_v2),
        )
        report_name = f"benchmark_compare_{args.dept}_{timestamp}.json"
    else:
        try:
            report = run_benchmark(
                mode=args.mode,
                department=args.dept,
                kb_path=_resolve_kb_path(args.kb),
                cases_dir=args.cases_dir,
            )
        except LLMNotConfiguredError as exc:
            raise SystemExit(str(exc)) from exc
        report_name = f"benchmark_{args.mode}_{args.dept}_{timestamp}.json"

    report_path = reports_dir / report_name
    save_json(report, report_path)

    if args.mode == "compare":
        print(f"Compare report written to {report_path}")
        print(f"KB v1 sensitivity: {report['kb_v1_metrics']['alert_sensitivity']}")
        print(f"KB v2 sensitivity: {report['kb_v2_metrics']['alert_sensitivity']}")
        return

    metrics = report["metrics"]
    print(f"Report written to {report_path}")
    print(f"Cases: {metrics['case_count']}")
    print(f"Alert sensitivity: {metrics['alert_sensitivity']}")
    print(f"Alert specificity: {metrics['alert_specificity']}")
    print(f"Risk level accuracy: {metrics['risk_level_accuracy']}")
    print(f"Block decision F1: {metrics['block_decision_f1']}")
    print(f"Alert attribution: {metrics['alert_attribution']}")
    boost = metrics.get("department_boost") or {}
    if boost.get("department_boost_accuracy") is not None:
        print(
            f"Department boost accuracy: {boost['department_boost_accuracy']} "
            f"({boost.get('department_boost_passed', 0)}/{boost.get('case_count', 0)})"
        )
    print(f"Stage11 clinical cases in run: {metrics.get('stage11_clinical_cases', 0)}")
    print(f"Stage11 negative cases in run: {metrics.get('stage11_negative_cases', 0)}")
    print(f"Failed cases: {metrics['failed_cases']}")
    if report["failures"]:
        for item in report["failures"][:10]:
            print(f"  - {item['case_id']}: missing={item['missing_required']}")


if __name__ == "__main__":
    main()
