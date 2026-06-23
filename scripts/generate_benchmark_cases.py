#!/usr/bin/env python3
"""Generate Stage 9 benchmark cases validated against the production knowledge base."""

from __future__ import annotations

import argparse
import sys
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.knowledge_base import SafetyKnowledgeBase
from src.review_engine import ReviewEngine
from src.schemas import CandidateDrug, PatientContext
from src.utils import save_json

DEFAULT_KB = PROJECT_ROOT / "data" / "knowledge" / "hospital_production_v4.json"
CASES_DIR = PROJECT_ROOT / "data" / "benchmark" / "cases"

DEPARTMENT_COUNTS: dict[str, int] = {
    "cardiology": 15,
    "respiratory": 10,
    "neurology": 12,
    "endocrinology": 10,
    "gastroenterology": 8,
    "nephrology": 8,
    "hematology": 8,
    "rheumatology": 8,
    "infectious": 8,
    "psychiatry": 6,
    "geriatrics": 6,
    "icu": 6,
    "obgyn": 5,
    "neurosurgery": 6,
    "radiology": 4,
    "oncology": 8,
    "emergency": 6,
    "general_internal": 6,
    "pediatrics": 5,
    "orthopedic": 5,
    "urology": 5,
    "anesthesiology": 5,
    "dermatology": 4,
    "ophthalmology": 3,
    "ent": 4,
    "rehabilitation": 4,
}

# Curated rule_ids chosen so ReviewEngine fires them against hospital_production_v4.json.
DEPARTMENT_RULES: dict[str, list[str]] = {
    "cardiology": [
        "ddi_warfarin_aspirin_bleeding",
        "ddi_warfarin_ibuprofen_bleeding",
        "ddi_digoxin_furosemide",
        "ddi_digoxin_amiodarone",
        "ddi_acei_spironolactone_lisinopril_spironolactone",
        "ddi_acei_arb_dual_lisinopril_losartan",
        "ddi_bb_ccb_metoprolol_verapamil",
        "ddi_clopidogrel_omeprazole",
        "ddi_warfarin_amiodarone",
        "ddi_doac_nsaids_ibuprofen_rivaroxaban",
        "ddi_doac_ssri_fluoxetine_rivaroxaban",
        "ddi_sotalol_qt_amiodarone_sotalol",
        "ddi_nitrate_pde5i_nitroglycerin_sildenafil",
        "ddi_heparin_warfarin_bleeding",
        "ddi_ticagrelor_simvastatin",
    ],
    "respiratory": [
        "ddi_sotalol_qt_azithromycin_sotalol",
        "ddi_sotalol_qt_moxifloxacin_sotalol",
        "ddi_clarithromycin_simvastatin_muscle",
        "alg_penicillin_amoxicillin",
        "ddi_warfarin_metronidazole",
        "ddi_warfarin_fluconazole",
        "pop_pediatric_levofloxacin",
        "ddi_aspirin_ibuprofen_antiplatelet",
        "ddi_heparin_ssri_enoxaparin_fluoxetine",
        "ddi_sotalol_qt_haloperidol_sotalol",
    ],
    "neurology": [
        "ddi_carbamazepine_cyp3a4i_carbamazepine_clarithromycin",
        "ddi_carbamazepine_valproate",
        "ddi_valproate_phenytoin",
        "ddi_ssri_tramadol_fluoxetine_tramadol",
        "ddi_ssri_triptan_fluoxetine_sumatriptan",
        "ddi_ssri_linezolid_fluoxetine_linezolid",
        "ddi_phenobarbital_inducer_phenobarbital_warfarin",
        "ddi_lithium_nsaids",
        "ddi_carbamazepine_cyp3a4i_carbamazepine_itraconazole",
        "ddi_ssri_maoi_fluoxetine_phenelzine",
        "ddi_opioid_benzo_diazepam_morphine",
        "ddi_antipsychotic_qt_haloperidol_moxifloxacin",
    ],
    "endocrinology": [
        "ddi_insulin_sulfonylurea_glibenclamide_insulin glargine",
        "ddi_metformin_contrast",
        "ddi_sglt2_diuretic_empagliflozin_furosemide",
        "pop_renal_metformin",
        "pop_renal_dabigatran",
        "ddi_levothyroxine_calcium",
        "ddi_levothyroxine_iron",
        "ddi_pioglitazone_insulin",
        "ddi_sglt2_diuretic_dapagliflozin_furosemide",
        "pop_lactation_lithium",
    ],
    "gastroenterology": [
        "ddi_omeprazole_methotrexate",
        "ddi_methotrexate_nsaids_gi",
        "ddi_sucralfate_quinolone",
        "ddi_metoclopramide_anticholinergic",
        "ddi_ursodeoxycholic_acid_antacid",
        "ddi_ibrutinib_ppi",
        "ddi_mycophenolate_ppi",
        "ddi_clopidogrel_omeprazole",
    ],
    "nephrology": [
        "pop_renal_metformin",
        "pop_renal_rivaroxaban",
        "pop_renal_vancomycin",
        "pop_renal_gentamicin",
        "ddi_acei_potassium_lisinopril_potassium chloride",
        "ddi_lithium_diuretics",
        "ddi_methotrexate_nsaids_gi",
        "pop_renal_spironolactone",
    ],
    "hematology": [
        "ddi_warfarin_fluconazole",
        "ddi_warfarin_metronidazole",
        "ddi_clopidogrel_anticoagulant_clopidogrel_warfarin",
        "ddi_clopidogrel_anticoagulant_clopidogrel_rivaroxaban",
        "ddi_methotrexate_tmp_smx",
        "ddi_heparin_warfarin_bleeding",
        "ddi_doac_nsaids_aspirin_dabigatran",
        "ddi_clopidogrel_anticoagulant_apixaban_clopidogrel",
    ],
    "rheumatology": [
        "ddi_methotrexate_leflunomide",
        "ddi_azathioprine_allopurinol",
        "ddi_cyclosporine_methotrexate",
        "ddi_colchicine_cyp3a4i_clarithromycin_colchicine",
        "ddi_methotrexate_nsaids_gi",
        "ddi_hcq_tamoxifen",
        "ddi_colchicine_cyp3a4i_colchicine_ketoconazole",
        "ddi_cyclophosphamide_allopurinol",
    ],
    "infectious": [
        "ddi_rifampin_warfarin",
        "ddi_rifampin_oral_contraceptives",
        "ddi_azole_statins_simvastatin_voriconazole",
        "ddi_azole_statins_atorvastatin_fluconazole",
        "ddi_methotrexate_tmp_smx",
        "ddi_ssri_linezolid_fluoxetine_linezolid",
        "alg_penicillin_amoxicillin",
        "ddi_warfarin_metronidazole",
    ],
    "psychiatry": [
        "ddi_lithium_acei",
        "ddi_lithium_diuretics",
        "ddi_lithium_nsaids",
        "ddi_maoi_tyramine",
        "ddi_clozapine_cyp1a2i_clozapine_fluvoxamine",
        "ddi_antipsychotic_qt_haloperidol_moxifloxacin",
    ],
    "geriatrics": [
        "pop_beers_diazepam",
        "pop_beers_glibenclamide",
        "pop_beers_digoxin",
        "pop_beers_amitriptyline",
        "ddi_geriatrics_fall_benzo_bp_diazepam_metoprolol",
        "ddi_geriatrics_anticholinergic_burden_diphenhydramine_oxybutynin",
    ],
    "icu": [
        "ddi_opioid_benzo_diazepam_fentanyl",
        "ddi_opioid_benzo_lorazepam_oxycodone",
        "ddi_icu_norepi_maoi_norepinephrine_phenelzine",
        "ddi_icu_propofol_lipid",
        "ddi_icu_sedative_nmb_midazolam_rocuronium",
        "ddi_icu_vasopressin_norepinephrine",
    ],
    "obgyn": [
        "pop_pregnancy_lisinopril",
        "pop_pregnancy_methotrexate",
        "pop_pregnancy_valproic acid",
        "pop_pregnancy_warfarin",
        "pop_pregnancy_levofloxacin",
    ],
    "neurosurgery": [
        "ddi_opioid_benzo_diazepam_morphine",
        "ddi_carbamazepine_valproate",
        "ddi_valproate_phenytoin",
        "ddi_carbamazepine_cyp3a4i_carbamazepine_clarithromycin",
        "ddi_antipsychotic_qt_haloperidol_moxifloxacin",
        "ddi_lithium_nsaids",
    ],
    "radiology": [
        "ddi_metformin_contrast",
        "pop_renal_metformin",
        "pop_renal_gentamicin",
        "pop_renal_rivaroxaban",
    ],
    "oncology": [
        "ddi_methotrexate_nsaids_gi",
        "ddi_methotrexate_leflunomide",
        "ddi_methotrexate_tmp_smx",
        "ddi_ibrutinib_ppi",
        "ddi_mycophenolate_ppi",
        "ddi_cyclophosphamide_allopurinol",
        "ddi_azathioprine_allopurinol",
        "ddi_hcq_tamoxifen",
    ],
    "emergency": [
        "ddi_opioid_benzo_diazepam_fentanyl",
        "ddi_warfarin_ibuprofen_bleeding",
        "ddi_sotalol_qt_moxifloxacin_sotalol",
        "alg_penicillin_amoxicillin",
        "ddi_heparin_ssri_enoxaparin_fluoxetine",
        "ddi_metformin_contrast",
    ],
    "general_internal": [
        "ddi_warfarin_aspirin_bleeding",
        "ddi_acei_arb_dual_lisinopril_losartan",
        "pop_renal_metformin",
        "ddi_clopidogrel_omeprazole",
        "ddi_levothyroxine_calcium",
        "ddi_clarithromycin_simvastatin_muscle",
    ],
    "pediatrics": [
        "pop_pediatric_aspirin",
        "pop_pediatric_levofloxacin",
        "pop_pediatric_codeine",
        "pop_pediatric_valproic_acid",
        "pop_pediatric_doxycycline",
    ],
    "orthopedic": [
        "ddi_warfarin_ibuprofen_bleeding",
        "ddi_aspirin_ibuprofen_antiplatelet",
        "ddi_methotrexate_nsaids_gi",
        "ddi_opioid_benzo_lorazepam_oxycodone",
        "ddi_doac_nsaids_ibuprofen_rivaroxaban",
    ],
    "urology": [
        "ddi_lithium_diuretics",
        "pop_renal_gentamicin",
        "ddi_acei_potassium_lisinopril_potassium chloride",
        "pop_renal_spironolactone",
        "pop_renal_metformin",
    ],
    "anesthesiology": [
        "ddi_icu_propofol_lipid",
        "ddi_opioid_benzo_diazepam_fentanyl",
        "ddi_icu_sedative_nmb_midazolam_rocuronium",
        "ddi_icu_vasopressin_norepinephrine",
        "ddi_opioid_benzo_lorazepam_oxycodone",
    ],
    "dermatology": [
        "ddi_methotrexate_nsaids_gi",
        "ddi_methotrexate_tmp_smx",
        "ddi_azathioprine_allopurinol",
        "alg_penicillin_amoxicillin",
    ],
    "ophthalmology": [
        "ddi_sotalol_qt_moxifloxacin_sotalol",
        "ddi_bb_ccb_metoprolol_verapamil",
        "ddi_antipsychotic_qt_haloperidol_moxifloxacin",
    ],
    "ent": [
        "alg_penicillin_amoxicillin",
        "ddi_clarithromycin_simvastatin_muscle",
        "ddi_metoclopramide_anticholinergic",
        "ddi_warfarin_metronidazole",
    ],
    "rehabilitation": [
        "pop_beers_diazepam",
        "ddi_geriatrics_fall_benzo_bp_diazepam_metoprolol",
        "ddi_geriatrics_anticholinergic_burden_diphenhydramine_oxybutynin",
        "pop_beers_amitriptyline",
    ],
}

DEPARTMENT_DESCRIPTIONS: dict[str, str] = {
    "cardiology": "心内科用药安全",
    "respiratory": "呼吸科用药安全",
    "neurology": "神经内科用药安全",
    "endocrinology": "内分泌科用药安全",
    "gastroenterology": "消化内科用药安全",
    "nephrology": "肾内科用药安全",
    "hematology": "血液科用药安全",
    "rheumatology": "风湿免疫科用药安全",
    "infectious": "感染科用药安全",
    "psychiatry": "精神科用药安全",
    "geriatrics": "老年科用药安全",
    "icu": "ICU/急诊用药安全",
    "obgyn": "妇产科用药安全",
    "neurosurgery": "神经外科用药安全",
    "radiology": "放射科用药安全",
    "oncology": "肿瘤科用药安全",
    "emergency": "急诊科用药安全",
    "general_internal": "普通内科用药安全",
    "pediatrics": "儿科用药安全",
    "orthopedic": "骨科用药安全",
    "urology": "泌尿外科用药安全",
    "anesthesiology": "麻醉科用药安全",
    "dermatology": "皮肤科用药安全",
    "ophthalmology": "眼科用药安全",
    "ent": "耳鼻喉科用药安全",
    "rehabilitation": "康复医学科用药安全",
}

DIFFICULTY_BY_RISK = {"high": "hard", "medium": "medium", "low": "easy", "none": "easy", "unknown": "hard"}


@dataclass
class RuleRecord:
    rule_id: str
    category: str
    rule: dict[str, Any]


@dataclass
class CaseBuildResult:
    case: dict[str, Any]
    fired_rule_ids: set[str]
    validation_errors: list[str] = field(default_factory=list)


def _drug_item(name: str) -> dict[str, str]:
    return {
        "name": name,
        "ingredient": name,
        "dose": "standard",
        "route": "PO",
        "frequency": "qd",
    }


def _candidate_item(name: str) -> dict[str, str]:
    item = _drug_item(name)
    item["source"] = "candidate"
    return item


def _lookup_rule(kb: SafetyKnowledgeBase, rule_id: str) -> RuleRecord | None:
    for category, key in (
        ("drug_interaction", "interaction_rules"),
        ("special_population", "population_rules"),
        ("allergy_contraindication", "allergy_rules"),
    ):
        for rule in kb.data.get(key, []):
            if rule.get("rule_id") == rule_id:
                return RuleRecord(rule_id=rule_id, category=category, rule=rule)
    return None


def _population_patient_overrides(rule: dict[str, Any]) -> dict[str, Any]:
    field_name = rule.get("population_field", "")
    overrides: dict[str, Any] = {"allergies": ["NKDA"], "missing_fields": []}

    if field_name == "pregnancy_status":
        overrides.update({"gender": "F", "age": 28, "pregnancy_status": "pregnant"})
    elif field_name in ("lactation", "lactation_status"):
        overrides.update(
            {
                "gender": "F",
                "age": 30,
                "pregnancy_status": "not_pregnant",
                "lactation_status": "lactating",
            }
        )
    elif field_name == "egfr":
        egfr_max = rule.get("egfr_max", 30)
        overrides["egfr"] = max(5.0, float(egfr_max) - 5.0)
    elif field_name == "hepatic":
        overrides["diagnoses"] = [{"icd9_code": "571.5", "name": "cirrhosis of liver"}]
    elif field_name == "age":
        age_min = rule.get("age_min")
        age_max = rule.get("age_max")
        age_compare = rule.get("age_compare", "lt")
        if age_compare == "gte" and age_min is not None:
            overrides["age"] = int(age_min) + 5
        elif age_compare == "lte" and age_max is not None:
            overrides["age"] = max(1, int(age_max) - 2)
        elif age_min is not None:
            overrides["age"] = max(1, int(age_min) - 2)
        elif age_max is not None:
            overrides["age"] = int(age_max) + 2
    return overrides


def _build_request_from_rule(
    rule_record: RuleRecord,
    subject_id: int,
    department: str,
) -> dict[str, Any]:
    rule = rule_record.rule
    category = rule_record.category
    patient: dict[str, Any] = {
        "subject_id": subject_id,
        "gender": "M",
        "age": 65,
        "diagnoses": [{"icd9_code": "799.9", "name": DEPARTMENT_DESCRIPTIONS.get(department, department)}],
        "current_medications": [],
        "allergies": ["NKDA"],
        "pregnancy_status": "not_applicable",
        "lactation_status": "not_lactating",
        "egfr": 90,
        "missing_fields": [],
    }
    candidate_drugs: list[dict[str, str]] = []

    if category == "drug_interaction":
        drugs = list(rule.get("drugs", []))
        if len(drugs) < 2:
            raise ValueError(f"interaction rule {rule_record.rule_id} needs 2 drugs")
        patient["current_medications"] = [_drug_item(drugs[0])]
        candidate_drugs = [_candidate_item(drugs[1])]
    elif category == "special_population":
        trigger = rule.get("trigger_drugs", [])
        if not trigger:
            raise ValueError(f"population rule {rule_record.rule_id} missing trigger_drugs")
        candidate_drugs = [_candidate_item(trigger[0])]
        patient.update(_population_patient_overrides(rule))
    elif category == "allergy_contraindication":
        trigger = rule.get("trigger_drugs", [])
        terms = rule.get("allergy_terms", [])
        if not trigger or not terms:
            raise ValueError(f"allergy rule {rule_record.rule_id} incomplete")
        candidate_drugs = [_candidate_item(trigger[0])]
        patient["allergies"] = [terms[0]]
        patient["gender"] = "F"
        patient["age"] = 45
        patient["pregnancy_status"] = "not_pregnant"
    else:
        raise ValueError(f"unsupported category {category}")

    return {"patient_context": patient, "candidate_drugs": candidate_drugs}


def _category_for_rule_id(rule_id: str) -> str:
    if rule_id.startswith(("ddi_", "mined_ddi_")):
        return "drug_interaction"
    if rule_id.startswith("pop_"):
        return "special_population"
    if rule_id.startswith("alg_"):
        return "allergy_contraindication"
    if rule_id.startswith("dup_"):
        return "duplicate_ingredient"
    return "drug_interaction"


def _validate_and_finalize_case(
    kb: SafetyKnowledgeBase,
    engine: ReviewEngine,
    department: str,
    rule_id: str,
    request: dict[str, Any],
    description: str,
    tags: list[str],
) -> CaseBuildResult:
    patient = PatientContext.model_validate(request["patient_context"])
    candidates = [CandidateDrug.model_validate(item) for item in request["candidate_drugs"]]
    output = engine.review(patient, candidates)
    fired = {item.rule_id for item in output.evidence}

    rule_record = _lookup_rule(kb, rule_id)
    expected_risk = rule_record.rule.get("risk_level", "high") if rule_record else "high"
    errors: list[str] = []
    if rule_id not in fired:
        errors.append(f"required rule {rule_id} did not fire; fired={sorted(fired)}")

    case_id = f"bench_{department}_{rule_id.replace(' ', '_')}"
    case = {
        "case_id": case_id,
        "department": department,
        "description": description,
        "difficulty": DIFFICULTY_BY_RISK.get(output.risk_level, "medium"),
        "tags": tags,
        "request": request,
        "ground_truth": {
            "risk_level": output.risk_level,
            "block_decision": output.block_decision,
            "required_alerts": [
                {
                    "rule_id": rule_id,
                    "category": _category_for_rule_id(rule_id),
                    "risk_level": expected_risk,
                    "must_fire": True,
                }
            ],
            "should_not_fire": [],
            "expected_overridable": output.risk_level != "high",
        },
    }
    return CaseBuildResult(case=case, fired_rule_ids=fired, validation_errors=errors)


def _description_for_rule(department: str, rule_id: str, rule_record: RuleRecord | None) -> str:
    if rule_record and rule_record.rule.get("summary"):
        return f"{DEPARTMENT_DESCRIPTIONS[department]}：{rule_record.rule['summary']}"
    return f"{DEPARTMENT_DESCRIPTIONS[department]}：{rule_id}"


def _tags_for_rule(rule_id: str, department: str) -> list[str]:
    tags = [department]
    if rule_id.startswith("ddi_"):
        tags.append("drug_interaction")
    elif rule_id.startswith("pop_"):
        tags.append("special_population")
    elif rule_id.startswith("alg_"):
        tags.append("allergy")
    if "warfarin" in rule_id or "doac" in rule_id or "anticoag" in rule_id:
        tags.append("anticoagulation")
    if "pregnancy" in rule_id:
        tags.append("pregnancy")
    if "beers" in rule_id or department == "geriatrics":
        tags.append("beers")
    return tags


def generate_cases(
    kb_path: Path,
    output_dir: Path,
    strict: bool = True,
    departments: list[str] | None = None,
) -> dict[str, Any]:
    kb = SafetyKnowledgeBase(kb_path)
    engine = ReviewEngine(kb=kb)
    output_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "kb_path": str(kb_path),
        "output_dir": str(output_dir),
        "departments": {},
        "total_cases": 0,
        "validation_failures": [],
    }

    subject_base = 50000
    case_index = 0

    for department, expected_count in DEPARTMENT_COUNTS.items():
        if departments and department not in departments:
            continue
        rule_ids = DEPARTMENT_RULES.get(department, [])
        if len(rule_ids) != expected_count:
            raise ValueError(
                f"department {department}: expected {expected_count} rules, got {len(rule_ids)}"
            )

        dept_written = 0
        for seq, rule_id in enumerate(rule_ids, start=1):
            rule_record = _lookup_rule(kb, rule_id)
            if rule_record is None:
                msg = f"{department}/{rule_id}: rule_id not found in KB"
                summary["validation_failures"].append(msg)
                if strict:
                    raise ValueError(msg)
                continue

            request = _build_request_from_rule(rule_record, subject_base + case_index, department)
            description = _description_for_rule(department, rule_id, rule_record)
            tags = _tags_for_rule(rule_id, department)
            result = _validate_and_finalize_case(
                kb, engine, department, rule_id, request, description, tags
            )

            if result.validation_errors:
                for err in result.validation_errors:
                    summary["validation_failures"].append(f"{department}/{rule_id}: {err}")
                if strict:
                    raise ValueError(result.validation_errors[0])

            case = deepcopy(result.case)
            case["case_id"] = f"bench_{department}_{seq:02d}_{rule_id.replace(' ', '_')}"
            filename = f"{case['case_id']}.json"
            save_json(case, output_dir / filename)
            dept_written += 1
            case_index += 1

        summary["departments"][department] = dept_written
        summary["total_cases"] += dept_written

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Stage 9 benchmark cases")
    parser.add_argument("--kb", type=Path, default=DEFAULT_KB, help="Knowledge base JSON path")
    parser.add_argument("--output", type=Path, default=CASES_DIR, help="Output directory for cases")
    parser.add_argument(
        "--strict",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Fail if any case does not fire its required rule",
    )
    parser.add_argument(
        "--departments",
        nargs="*",
        metavar="DEPT",
        help="Generate only listed departments (default: all)",
    )
    args = parser.parse_args()

    summary = generate_cases(
        args.kb,
        args.output,
        strict=args.strict,
        departments=args.departments or None,
    )
    print(f"Generated {summary['total_cases']} benchmark cases in {args.output}")
    for dept, count in summary["departments"].items():
        print(f"  {dept}: {count}")
    if summary["validation_failures"]:
        print(f"Validation failures: {len(summary['validation_failures'])}")
        for item in summary["validation_failures"][:20]:
            print(f"  - {item}")


if __name__ == "__main__":
    main()
