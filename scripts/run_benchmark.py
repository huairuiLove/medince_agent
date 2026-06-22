#!/usr/bin/env python3
"""Run Stage 9 benchmark evaluation against benchmark cases."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

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
)
from src.utils import load_json, save_json

DEFAULT_KB = PROJECT_ROOT / "data" / "knowledge" / "hospital_production_v4.json"
CASES_DIR = PROJECT_ROOT / "data" / "benchmark" / "cases"
REPORTS_DIR = PROJECT_ROOT / "data" / "benchmark" / "reports"

KB_ALIASES: dict[str, Path] = {
    "expanded_mined_v1": PROJECT_ROOT / "data" / "knowledge" / "expanded_drug_safety_rules.json",
    "internal_medicine_full": PROJECT_ROOT / "data" / "knowledge" / "hospital_production_v4.json",
    "hospital_production_v4": PROJECT_ROOT / "data" / "knowledge" / "hospital_production_v4.json",
    "minimal": PROJECT_ROOT / "data" / "knowledge" / "minimal_drug_safety_rules.json",
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


def _run_rule_review(case: dict[str, Any], engine: ReviewEngine) -> dict[str, Any]:
    request = case["request"]
    patient = PatientContext.model_validate(request["patient_context"])
    candidates = [CandidateDrug.model_validate(item) for item in request.get("candidate_drugs", [])]
    output = engine.review(patient, candidates)
    return _output_to_actual(output, candidates)


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
    patient = PatientContext.model_validate(request["patient_context"])
    candidates = [CandidateDrug.model_validate(item) for item in request.get("candidate_drugs", [])]
    engine = ReviewEngine(kb=SafetyKnowledgeBase(kb_path))
    orchestrator = MultiAgentOrchestrator()
    orchestrator.review_engine = engine
    multi = orchestrator.run(patient, candidates, skip_clarify=True)
    actual = _output_to_actual(multi.rule_output, candidates)
    actual["risk_level"] = multi.arbitration.consensus_risk_level
    actual["block_decision"] = multi.arbitration.consensus_block_decision
    return actual


def normalize_name(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


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
        "passed": not (
            fn > 0
            or fp > 0
            or actual["risk_level"] != gt.get("risk_level")
            or actual["block_decision"] != gt.get("block_decision")
        ),
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

    engine = ReviewEngine(kb=SafetyKnowledgeBase(kb_path))
    case_results: list[dict[str, Any]] = []
    for case in cases:
        if mode == "rule-only":
            actual = _run_rule_review(case, engine)
        elif mode == "cpoe":
            actual = _run_cpoe_review(case, kb_path)
        elif mode == "full-pipeline":
            actual = _run_full_pipeline_review(case, kb_path)
        else:
            raise SystemExit(f"Unsupported mode: {mode}")

        case_results.append(_evaluate_case(case, actual))

    metrics = _aggregate(case_results)
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
        default="internal_medicine_full",
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
    print(f"Failed cases: {metrics['failed_cases']}")
    if report["failures"]:
        for item in report["failures"][:10]:
            print(f"  - {item['case_id']}: missing={item['missing_required']}")


if __name__ == "__main__":
    main()
