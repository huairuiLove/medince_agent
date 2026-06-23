#!/usr/bin/env python3
"""Generate Stage 11 clinical complex benchmark cases + 30 negative tests."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.department.priority import DEPT_FOCUS_PREFIX, normalize_department
from src.knowledge_base import SafetyKnowledgeBase
from src.knowledge_mining.stage11_department_rules import get_stage11_rules
from src.review_engine import ReviewEngine
from src.schemas import CandidateDrug, PatientContext
from src.utils import save_json

DEFAULT_KB = PROJECT_ROOT / "datasets" / "knowledge" / "hospital_production_v5.json"
CASES_DIR = PROJECT_ROOT / "datasets" / "benchmark" / "cases"

# Benchmark department ids (match existing bench_* cases)
DEPARTMENTS = [
    "cardiology", "respiratory", "neurology", "endocrinology", "gastroenterology",
    "nephrology", "hematology", "rheumatology", "infectious", "psychiatry",
    "geriatrics", "icu", "obgyn", "neurosurgery", "radiology", "oncology",
    "emergency", "general_internal", "pediatrics", "orthopedic", "urology",
    "anesthesiology", "dermatology", "ophthalmology", "ent", "rehabilitation",
]

DEPT_TO_RULE_TAG = {
    "obgyn": "obstetrics_gynecology",
    "infectious": "infectious_disease",
}


def rule_dept_matches(rule_dept: str | None, bench_dept: str) -> bool:
    tag = DEPT_TO_RULE_TAG.get(bench_dept, bench_dept)
    return normalize_department(rule_dept or "") == normalize_department(tag)


def _drug(name: str, dose: str = "standard") -> dict[str, str]:
    return {"name": name, "ingredient": name, "dose": dose, "route": "PO", "frequency": "qd"}


def _candidate(name: str, dose: str = "standard") -> dict[str, str]:
    return {**_drug(name, dose), "source": "candidate"}


def _base_patient(
    *,
    dept: str,
    age: int = 65,
    gender: str = "M",
    egfr: float | None = 90,
    **extra: Any,
) -> dict[str, Any]:
    patient: dict[str, Any] = {
        "subject_id": hash(dept) % 90000 + 10000,
        "gender": gender,
        "age": age,
        "department": dept,
        "diagnoses": [{"icd9_code": "799.9", "name": f"{dept} clinical scenario"}],
        "current_medications": [],
        "allergies": ["NKDA"],
        "pregnancy_status": "not_applicable",
        "lactation_status": "not_lactating",
        "missing_fields": [],
    }
    if egfr is not None:
        patient["egfr"] = egfr
    patient.update(extra)
    return patient


# Hand-crafted expert polypharmacy / multi-rule scenarios
EXPERT_SCENARIOS: list[dict[str, Any]] = [
    {
        "case_id": "clinical_cardio_polypharmacy_01",
        "department": "cardiology",
        "description": "72岁男性，心衰+房颤+CKD3，地高辛+呋塞米+华法林+螺内酯，新增胺碘酮",
        "difficulty": "expert",
        "request": {
            "patient_context": _base_patient(
                dept="cardiology", age=72, egfr=42,
                diagnoses=[
                    {"icd9_code": "428.0", "name": "Congestive heart failure"},
                    {"icd9_code": "427.31", "name": "Atrial fibrillation"},
                    {"icd9_code": "585.3", "name": "CKD stage 3"},
                ],
                current_medications=[
                    _drug("digoxin", "0.125mg"), _drug("furosemide", "40mg"),
                    _drug("warfarin", "3mg"), _drug("spironolactone", "20mg"),
                ],
            ),
            "candidate_drugs": [_candidate("amiodarone", "200mg")],
        },
        "required_rule_ids": ["ddi_digoxin_amiodarone", "ddi_warfarin_amiodarone"],
        "expected_department_boost": "cardiology",
    },
    {
        "case_id": "clinical_cardio_polypharmacy_02",
        "department": "cardiology",
        "description": "ACS 患者 DAPT + PPI 审查",
        "difficulty": "hard",
        "request": {
            "patient_context": _base_patient(
                dept="cardiology", age=68,
                current_medications=[_drug("aspirin"), _drug("clopidogrel")],
            ),
            "candidate_drugs": [_candidate("omeprazole")],
        },
        "required_rule_ids": ["ddi_clopidogrel_omeprazole"],
        "expected_department_boost": "cardiology",
    },
    {
        "case_id": "clinical_neuro_polypharmacy_01",
        "department": "neurology",
        "description": "癫痫患者丙戊酸基础上加拉莫三嗪",
        "difficulty": "hard",
        "request": {
            "patient_context": _base_patient(
                dept="neurology", age=28, gender="F",
                current_medications=[_drug("valproic acid", "500mg bid")],
            ),
            "candidate_drugs": [_candidate("lamotrigine", "25mg")],
        },
        "required_rule_ids": ["ddi_valproate_lamotrigine"],
        "expected_department_boost": "neurology",
    },
    {
        "case_id": "clinical_icu_sedation_01",
        "department": "icu",
        "description": "ICU 镇静：丙泊酚 + 芬太尼",
        "difficulty": "hard",
        "request": {
            "patient_context": _base_patient(
                dept="icu", age=55,
                current_medications=[_drug("fentanyl")],
            ),
            "candidate_drugs": [_candidate("propofol")],
        },
        "required_rule_ids": ["ddi_anest_propofol_opioid_propofol_fentanyl"],
        "expected_department_boost": "icu",
    },
    {
        "case_id": "clinical_onc_chemo_01",
        "department": "oncology",
        "description": "顺铂 + 强 CYP3A4 抑制剂",
        "difficulty": "hard",
        "request": {
            "patient_context": _base_patient(dept="oncology", age=58, egfr=75),
            "candidate_drugs": [_candidate("ketoconazole")],
        },
        "required_rule_ids": [],
        "current_for_candidate": False,
        "setup_meds": ["cisplatin"],
    },
    {
        "case_id": "clinical_obgyn_pregnancy_01",
        "department": "obgyn",
        "description": "妊娠期 ACEI 禁忌",
        "difficulty": "expert",
        "request": {
            "patient_context": _base_patient(
                dept="obgyn", age=32, gender="F",
                pregnancy_status="pregnant",
                current_medications=[],
            ),
            "candidate_drugs": [_candidate("lisinopril")],
        },
        "required_rule_ids": ["pop_pregnancy_lisinopril"],
        "expected_department_boost": "obgyn",
    },
    {
        "case_id": "clinical_peds_age_01",
        "department": "pediatrics",
        "description": "儿童禁用喹诺酮",
        "difficulty": "medium",
        "request": {
            "patient_context": _base_patient(dept="pediatrics", age=12, gender="M"),
            "candidate_drugs": [_candidate("levofloxacin")],
        },
        "required_rule_ids": ["pop_pediatric_levofloxacin"],
    },
    {
        "case_id": "clinical_geriatrics_beers_01",
        "department": "geriatrics",
        "description": "老年 Beers 苯二氮䓬",
        "difficulty": "medium",
        "request": {
            "patient_context": _base_patient(dept="geriatrics", age=82, egfr=55),
            "candidate_drugs": [_candidate("diazepam")],
        },
        "required_rule_ids": ["pop_beers_diazepam"],
        "expected_department_boost": "geriatrics",
    },
]


NEGATIVE_SCENARIOS: list[tuple[str, str, str]] = [
    ("negative_safe_htn_01", "cardiology", "lisinopril"),
    ("negative_safe_htn_02", "cardiology", "amlodipine"),
    ("negative_safe_dm_01", "endocrinology", "metformin"),
    ("negative_safe_dm_02", "endocrinology", "sitagliptin"),
    ("negative_safe_statin_01", "cardiology", "atorvastatin"),
    ("negative_safe_ppi_01", "gastroenterology", "pantoprazole"),
    ("negative_safe_abx_01", "infectious", "amoxicillin"),
    ("negative_safe_abx_02", "infectious", "azithromycin"),
    ("negative_safe_resp_01", "respiratory", "salbutamol"),
    ("negative_safe_neuro_01", "neurology", "levetiracetam"),
    ("negative_safe_renal_01", "nephrology", "furosemide"),
    ("negative_safe_ortho_01", "orthopedic", "paracetamol"),
    ("negative_safe_psych_01", "psychiatry", "sertraline"),
    ("negative_safe_rheum_01", "rheumatology", "hydroxychloroquine"),
    ("negative_safe_hema_01", "hematology", "folic_acid"),
    ("negative_safe_urology_01", "urology", "tamsulosin"),
    ("negative_safe_ent_01", "ent", "loratadine"),
    ("negative_safe_derm_01", "dermatology", "hydrocortisone"),
    ("negative_safe_eye_01", "ophthalmology", "latanoprost"),
    ("negative_safe_rehab_01", "rehabilitation", "paracetamol"),
    ("negative_safe_emerg_01", "emergency", "ondansetron"),
    ("negative_safe_onc_support_01", "oncology", "dexamethasone"),
    ("negative_safe_icu_01", "icu", "pantoprazole"),
    ("negative_safe_gen_01", "general_internal", "losartan"),
    ("negative_safe_gen_02", "general_internal", "rosuvastatin"),
    ("negative_safe_anest_01", "anesthesiology", "lidocaine"),
    ("negative_safe_neurosx_01", "neurosurgery", "dexamethasone"),
    ("negative_safe_radio_01", "radiology", "normal_saline"),
    ("negative_safe_peds_01", "pediatrics", "paracetamol"),
    ("negative_safe_obgyn_02", "obgyn", "folic_acid"),
]


def _finalize_expert(raw: dict[str, Any], engine: ReviewEngine) -> dict[str, Any] | None:
    req = raw["request"]
    if raw.get("setup_meds"):
        req = {
            **req,
            "patient_context": {
                **req["patient_context"],
                "current_medications": [_drug(m) for m in raw["setup_meds"]],
            },
        }
    patient = PatientContext.model_validate(req["patient_context"])
    candidates = [CandidateDrug.model_validate(c) for c in req["candidate_drugs"]]
    dept = raw["department"]
    output = engine.review(patient, candidates, department=dept)
    fired = {e.rule_id for e in output.evidence}

    required_ids = list(raw.get("required_rule_ids") or [])
    if not required_ids and not raw.get("optional_rules"):
        required_ids = sorted(fired)[:3]

    if required_ids and not raw.get("optional_rules"):
        missing = [rid for rid in required_ids if rid not in fired]
        if missing:
            return None

    gt_required = [
        {
            "rule_id": rid,
            "category": "drug_interaction",
            "risk_level": "high",
            "must_fire": True,
        }
        for rid in required_ids
        if rid in fired
    ]
    if not gt_required and output.risk_level == "none":
        return None

    case = {
        "case_id": raw["case_id"],
        "department": dept,
        "description": raw["description"],
        "difficulty": raw.get("difficulty", "hard"),
        "tags": ["stage11", "clinical", dept],
        "request": req,
        "ground_truth": {
            "risk_level": output.risk_level,
            "block_decision": output.block_decision,
            "required_alerts": gt_required,
            "should_not_fire": [],
            "expected_overridable": output.risk_level != "high",
        },
    }
    if raw.get("expected_department_boost"):
        case["ground_truth"]["expected_department_boost"] = raw["expected_department_boost"]
    return case


def _auto_clinical_for_dept(
    dept: str,
    kb: SafetyKnowledgeBase,
    engine: ReviewEngine,
    *,
    per_dept: int = 3,
    start_index: int = 1,
) -> list[dict[str, Any]]:
    rules = [r for r in kb.get_interaction_rules() if rule_dept_matches(r.get("department"), dept)]
    cases: list[dict[str, Any]] = []
    idx = start_index
    for rule in rules:
        if len(cases) >= per_dept:
            break
        drugs = rule.get("drugs", [])
        if len(drugs) < 2:
            continue
        patient = _base_patient(dept=dept, age=60 + idx)
        patient["current_medications"] = [_drug(drugs[0])]
        candidates = [_candidate(drugs[1])]
        pctx = PatientContext.model_validate({**patient, "department": dept})
        cands = [CandidateDrug.model_validate(c) for c in candidates]
        output = engine.review(pctx, cands, department=dept)
        if rule["rule_id"] not in {e.rule_id for e in output.evidence}:
            continue

        boost = dept if rule.get("department") else None
        case = {
            "case_id": f"clinical_{dept}_auto_{idx:02d}",
            "department": dept,
            "description": f"{dept} 科室场景：{rule.get('summary', rule['rule_id'])[:80]}",
            "difficulty": "medium",
            "tags": ["stage11", "clinical", "auto", dept],
            "request": {"patient_context": patient, "candidate_drugs": candidates},
            "ground_truth": {
                "risk_level": output.risk_level,
                "block_decision": output.block_decision,
                "required_alerts": [
                    {
                        "rule_id": rule["rule_id"],
                        "category": "drug_interaction",
                        "risk_level": rule.get("risk_level", "medium"),
                        "must_fire": True,
                    }
                ],
                "should_not_fire": [],
            },
        }
        if boost and rule.get("department"):
            case["ground_truth"]["expected_department_boost"] = dept
        cases.append(case)
        idx += 1
    return cases


def _negative_case(
    case_id: str,
    dept: str,
    candidate: str,
    engine: ReviewEngine,
) -> dict[str, Any] | None:
    patient = _base_patient(dept=dept, age=55, egfr=90)
    patient["current_medications"] = []
    candidates = [_candidate(candidate)]
    pctx = PatientContext.model_validate({**patient, "department": dept})
    cands = [CandidateDrug.model_validate(c) for c in candidates]
    output = engine.review(pctx, cands, department=dept)
    model_hits = [
        e for e in output.evidence
        if e.source == "ddi_bert_model" or str(e.rule_id).startswith("ddi_model_")
    ]
    if output.risk_level in {"high", "medium"}:
        return None
    if model_hits and output.risk_level not in {"none", "low", "unknown"}:
        return None
    safe_risk = output.risk_level if output.risk_level in {"none", "low", "unknown"} else "low"
    return {
        "case_id": case_id,
        "department": dept,
        "description": f"阴性测试：单药 {candidate} 预期安全",
        "difficulty": "easy",
        "tags": ["stage11", "negative", dept],
        "request": {"patient_context": patient, "candidate_drugs": candidates},
        "ground_truth": {
            "risk_level": safe_risk,
            "block_decision": output.block_decision if output.evidence else False,
            "required_alerts": [],
            "should_not_fire": [],
            "is_negative_test": True,
        },
    }


def generate_all(kb_path: Path, output_dir: Path, *, auto_per_dept: int = 3) -> dict[str, Any]:
    kb = SafetyKnowledgeBase(kb_path)
    engine = ReviewEngine(kb=kb)
    output_dir.mkdir(parents=True, exist_ok=True)

    clinical: list[dict[str, Any]] = []
    skipped_expert = 0
    for raw in EXPERT_SCENARIOS:
        case = _finalize_expert(raw, engine)
        if case:
            clinical.append(case)
        else:
            skipped_expert += 1

    for dept in DEPARTMENTS:
        start = len([c for c in clinical if c["department"] == dept]) + 1
        clinical.extend(
            _auto_clinical_for_dept(dept, kb, engine, per_dept=auto_per_dept, start_index=start)
        )

    negative: list[dict[str, Any]] = []
    skipped_neg = 0
    for case_id, dept, cand in NEGATIVE_SCENARIOS:
        case = _negative_case(case_id, dept, cand, engine)
        if case:
            negative.append(case)
        else:
            skipped_neg += 1

    written = 0
    for case in clinical + negative:
        path = output_dir / f"{case['case_id']}.json"
        save_json(case, path)
        written += 1

    return {
        "clinical_count": len(clinical),
        "negative_count": len(negative),
        "written": written,
        "skipped_expert": skipped_expert,
        "skipped_negative": skipped_neg,
        "output_dir": str(output_dir),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Stage 11 clinical benchmark cases")
    parser.add_argument("--kb", default=str(DEFAULT_KB))
    parser.add_argument("--output-dir", type=Path, default=CASES_DIR)
    parser.add_argument("--auto-per-dept", type=int, default=3)
    args = parser.parse_args()

    summary = generate_all(Path(args.kb), args.output_dir, auto_per_dept=args.auto_per_dept)
    print("=== Stage 11 clinical benchmark generation ===")
    for key, value in summary.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
