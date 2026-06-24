"""Generate case template fixtures and MIMIC-III patient contexts for integration testing."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

MIMIC_CANDIDATE_DIRS = (
    PROJECT_ROOT / "datasets" / "mimic-iii-clinical-database-1.4",
    PROJECT_ROOT / "datasets" / "raw" / "mimiciii",
    PROJECT_ROOT / "datasets" / "external" / "mimiciii-demo",
)


def generate_review_cases():
    """Generate 3 review demo cases."""
    demo_dir = PROJECT_ROOT / "datasets" / "case_templates"
    demo_dir.mkdir(parents=True, exist_ok=True)

    # Case 1: High risk - warfarin + ibuprofen interaction
    case1 = {
        "case_id": "demo_review_01",
        "description": "高风险相互作用：华法林 + 布洛芬出血风险",
        "request": {
            "patient_context": {
                "subject_id": 10001,
                "hadm_id": 20001,
                "gender": "M",
                "age": 67,
                "admission_type": "EMERGENCY",
                "source_text": "患者男性67岁，因胸痛和呼吸困难入院。既往冠心病、房颤病史，长期口服华法林。",
                "chief_complaint": "胸痛和呼吸困难",
                "history_present_illness": "呼吸困难加重2天，既往冠心病和高血压病史",
                "symptoms_or_complaints": ["胸痛", "呼吸困难"],
                "past_medical_history": ["冠心病", "高血压", "房颤"],
                "diagnoses": [
                    {"icd9_code": "410.71", "name": "心内膜下心肌梗死"},
                    {"icd9_code": "401.9", "name": "高血压"}
                ],
                "current_medications": [
                    {"name": "warfarin", "ingredient": "warfarin", "dose": "5mg", "route": "PO", "frequency": "qd"},
                    {"name": "aspirin", "ingredient": "aspirin", "dose": "81mg", "route": "PO", "frequency": "qd"}
                ],
                "allergies": [],
                "pregnancy_status": "not_applicable",
                "missing_fields": ["allergies"]
            },
            "candidate_drugs": [
                {"name": "ibuprofen", "ingredient": "ibuprofen", "dose": "400mg", "route": "PO", "frequency": "tid",
                 "indication": "胸痛", "source": "candidate"}
            ],
            "persist": True
        },
        "expected": {
            "risk_level": "high",
            "block_decision": True,
            "need_clarification": True,
            "should_hit_ddi": True,
            "should_hit_dup": False
        }
    }

    # Case 2: Allergy info missing - amoxicillin
    case2 = {
        "case_id": "demo_review_02",
        "description": "过敏信息缺失：阿莫西林候选，过敏史未知",
        "request": {
            "patient_context": {
                "subject_id": 10002,
                "hadm_id": 20002,
                "gender": "F",
                "age": 34,
                "admission_type": "URGENT",
                "source_text": "患者女性34岁，因发热咳嗽3天入院，诊断为社区获得性肺炎。",
                "chief_complaint": "发热咳嗽",
                "history_present_illness": "发热咳嗽3天",
                "symptoms_or_complaints": ["发热", "咳嗽", "咳痰"],
                "past_medical_history": [],
                "diagnoses": [
                    {"icd9_code": "486", "name": "肺炎"}
                ],
                "current_medications": [],
                "allergies": [],
                "pregnancy_status": "unknown",
                "missing_fields": ["allergies", "current_medications", "pregnancy_status"]
            },
            "candidate_drugs": [
                {"name": "amoxicillin", "ingredient": "amoxicillin", "dose": "500mg", "route": "PO", "frequency": "tid",
                 "indication": "社区获得性肺炎", "source": "candidate"}
            ],
            "persist": True
        },
        "expected": {
            "risk_level": "unknown",
            "block_decision": True,
            "need_clarification": True,
            "should_hit_allergy": False,
            "clarification_targets_include": ["allergies", "pregnancy_status"]
        }
    }

    # Case 3: Pregnancy contraindication - lisinopril
    case3 = {
        "case_id": "demo_review_03",
        "description": "妊娠相关禁忌：育龄女性，妊娠状态未知，候选药物lisinopril",
        "request": {
            "patient_context": {
                "subject_id": 10003,
                "hadm_id": 20003,
                "gender": "F",
                "age": 28,
                "admission_type": "URGENT",
                "source_text": "患者女性28岁，因头晕头痛入院，血压偏高。",
                "chief_complaint": "头晕头痛",
                "history_present_illness": "反复头晕头痛1周",
                "symptoms_or_complaints": ["头晕", "头痛"],
                "past_medical_history": [],
                "diagnoses": [
                    {"icd9_code": "401.9", "name": "高血压"}
                ],
                "current_medications": [],
                "allergies": [],
                "pregnancy_status": "unknown",
                "missing_fields": ["allergies", "current_medications", "pregnancy_status"]
            },
            "candidate_drugs": [
                {"name": "lisinopril", "ingredient": "lisinopril", "dose": "10mg", "route": "PO", "frequency": "qd",
                 "indication": "高血压", "source": "candidate"}
            ],
            "persist": True
        },
        "expected": {
            "risk_level": "unknown",
            "block_decision": True,
            "need_clarification": True,
            "clarification_targets_include": ["pregnancy_status", "allergies", "current_medications"]
        }
    }

    with open(demo_dir / "review_case_01.json", "w", encoding="utf-8") as f:
        json.dump(case1, f, ensure_ascii=False, indent=2)
    with open(demo_dir / "review_case_02.json", "w", encoding="utf-8") as f:
        json.dump(case2, f, ensure_ascii=False, indent=2)
    with open(demo_dir / "review_case_03.json", "w", encoding="utf-8") as f:
        json.dump(case3, f, ensure_ascii=False, indent=2)
    print("Created 3 review demo cases.")


def generate_clarify_cases():
    """Generate clarify demo cases."""
    demo_dir = PROJECT_ROOT / "datasets" / "case_templates"
    demo_dir.mkdir(parents=True, exist_ok=True)

    # Clarify case 1: need_user_input - missing allergy and pregnancy
    clarify1 = {
        "case_id": "demo_clarify_01",
        "description": "追问模式：过敏和妊娠状态缺失",
        "request": {
            "patient_context": {
                "subject_id": 10004,
                "hadm_id": 20004,
                "gender": "F",
                "age": 26,
                "admission_type": "URGENT",
                "chief_complaint": "发热咽痛",
                "symptoms_or_complaints": ["发热", "咽痛"],
                "diagnoses": [{"icd9_code": "462", "name": "急性咽炎"}],
                "current_medications": [],
                "allergies": [],
                "pregnancy_status": "unknown",
                "missing_fields": ["allergies", "pregnancy_status", "current_medications"]
            },
            "candidate_drugs": [
                {"name": "amoxicillin", "ingredient": "amoxicillin", "dose": "500mg", "route": "PO",
                 "indication": "急性咽炎", "source": "candidate"}
            ],
            "review_output": {
                "risk_level": "unknown",
                "block_decision": True,
                "risk_reasons": [],
                "alternative_suggestions": [],
                "need_clarification": True,
                "clarification_targets": ["allergies", "pregnancy_status", "current_medications"],
                "evidence": [],
                "final_recommendation": "当前信息不足，建议先补充关键字段后再继续用药审查。"
            },
            "unable_to_answer": False,
            "persist": True
        },
        "expected": {
            "status": "need_user_input",
            "question_count_min": 2,
            "priority_fields": ["allergies", "pregnancy_status"]
        }
    }

    # Clarify case 2: conservative_fallback - unable to answer
    clarify2 = {
        "case_id": "demo_clarify_02",
        "description": "保守降级模式：用户无法补充信息",
        "request": {
            "patient_context": {
                "subject_id": 10005,
                "hadm_id": 20005,
                "gender": "F",
                "age": 31,
                "admission_type": "EMERGENCY",
                "chief_complaint": "严重腹痛",
                "symptoms_or_complaints": ["腹痛", "恶心"],
                "diagnoses": [{"icd9_code": "789.0", "name": "腹痛待查"}],
                "current_medications": [{"name": "warfarin", "ingredient": "warfarin", "dose": "3mg", "route": "PO"}],
                "allergies": [],
                "pregnancy_status": "unknown",
                "missing_fields": ["allergies", "pregnancy_status"]
            },
            "candidate_drugs": [
                {"name": "ibuprofen", "ingredient": "ibuprofen", "dose": "400mg", "route": "PO",
                 "indication": "腹痛", "source": "candidate"}
            ],
            "review_output": {
                "risk_level": "high",
                "block_decision": True,
                "risk_reasons": ["华法林与布洛芬联用增加严重出血风险。"],
                "alternative_suggestions": ["可优先评估对乙酰氨基酚等替代止痛方案。"],
                "need_clarification": True,
                "clarification_targets": ["allergies", "pregnancy_status"],
                "evidence": [
                    {
                        "rule_id": "ddi_warfarin_ibuprofen_bleeding",
                        "category": "drug_interaction",
                        "risk_level": "high",
                        "summary": "华法林与布洛芬联用增加严重出血风险。",
                        "mechanism": "抗凝作用与NSAIDs出血风险叠加。",
                        "implicated_drugs": ["ibuprofen", "warfarin"],
                        "recommendation": "避免联用。",
                        "alternatives": ["对乙酰氨基酚"],
                        "clarification_fields": ["current_medications"]
                    }
                ],
                "final_recommendation": "当前候选用药存在高风险，建议先阻断该方案。"
            },
            "unable_to_answer": True,
            "persist": True
        },
        "expected": {
            "status": "conservative_fallback",
            "has_conservative_advice": True,
            "has_disclaimer": True
        }
    }

    with open(demo_dir / "clarify_case_01.json", "w", encoding="utf-8") as f:
        json.dump(clarify1, f, ensure_ascii=False, indent=2)
    with open(demo_dir / "clarify_case_02.json", "w", encoding="utf-8") as f:
        json.dump(clarify2, f, ensure_ascii=False, indent=2)
    print("Created 2 clarify demo cases.")


def generate_consult_case():
    """Generate full consult demo case."""
    demo_dir = PROJECT_ROOT / "datasets" / "case_templates"
    demo_dir.mkdir(parents=True, exist_ok=True)

    consult1 = {
        "case_id": "demo_consult_01",
        "description": "完整会诊：直接传patient_context，跳过extract",
        "request": {
            "patient_context": {
                "subject_id": 10006,
                "hadm_id": 20006,
                "gender": "F",
                "age": 35,
                "admission_type": "EMERGENCY",
                "chief_complaint": "剧烈头痛伴视力模糊",
                "symptoms_or_complaints": ["头痛", "视力模糊", "恶心"],
                "past_medical_history": ["高血压"],
                "diagnoses": [
                    {"icd9_code": "401.9", "name": "高血压"},
                    {"icd9_code": "346.9", "name": "偏头痛"}
                ],
                "current_medications": [
                    {"name": "propranolol", "ingredient": "propranolol", "dose": "40mg", "route": "PO", "frequency": "bid"}
                ],
                "allergies": ["penicillin"],
                "pregnancy_status": "unknown",
                "missing_fields": ["pregnancy_status"]
            },
            "candidate_drugs": [
                {"name": "lisinopril", "ingredient": "lisinopril", "dose": "10mg", "route": "PO", "frequency": "qd",
                 "indication": "高血压", "source": "candidate"},
                {"name": "ibuprofen", "ingredient": "ibuprofen", "dose": "200mg", "route": "PO", "frequency": "prn",
                 "indication": "头痛", "source": "candidate"}
            ],
            "unable_to_answer": False,
            "persist": True
        },
        "expected": {
            "should_perform_review": True,
            "should_perform_clarify": True,
            "should_have_final_recommendation": True
        }
    }

    with open(demo_dir / "consult_case_01.json", "w", encoding="utf-8") as f:
        json.dump(consult1, f, ensure_ascii=False, indent=2)
    print("Created 1 consult demo case.")


def resolve_mimic_raw_dir() -> Path | None:
    for path in MIMIC_CANDIDATE_DIRS:
        if (path / "PATIENTS.csv").is_file() and (path / "ADMISSIONS.csv").is_file():
            return path
    return None


def is_full_mimic_dataset(raw_dir: Path) -> bool:
    rx = raw_dir / "PRESCRIPTIONS.csv"
    return rx.is_file() and rx.stat().st_size >= 50_000_000


def generate_mimic_patient_contexts(
    *,
    max_samples: int = 0,
    skip_notes: bool = False,
    require_medications: bool = True,
    include_labs: bool = True,
    include_icu: bool = True,
    include_imaging: bool = True,
) -> None:
    """Build patient contexts from real MIMIC-III CSV tables (no synthetic fallback)."""
    raw_dir = resolve_mimic_raw_dir()
    if raw_dir is None:
        raise FileNotFoundError(
            "MIMIC-III CSV not found. Expected PATIENTS.csv + ADMISSIONS.csv under "
            "datasets/mimic-iii-clinical-database-1.4/ or datasets/raw/mimiciii/."
        )

    processed_dir = PROJECT_ROOT / "datasets" / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    output_path = processed_dir / "mimiciii_patient_contexts.json"

    cmd = [
        sys.executable,
        "-m",
        "src.build_mimic_samples",
        "--raw_dir",
        str(raw_dir),
        "--out_path",
        str(output_path),
        "--max_samples",
        str(max_samples),
    ]
    if skip_notes:
        cmd.append("--skip-notes")
    if require_medications:
        cmd.append("--require-medications")
    if include_labs:
        cmd.append("--include-labs")
    else:
        cmd.append("--no-labs")
    if include_icu:
        cmd.append("--include-icu")
    if include_imaging:
        cmd.append("--include-imaging")

    print(f"Building patient contexts from {raw_dir.relative_to(PROJECT_ROOT)} ...")
    if max_samples == 0:
        print("  max_samples=0 → exporting ALL admissions matching filters (may take 30–90 min on full 1.4)")
    subprocess.run(cmd, check=True, cwd=PROJECT_ROOT)

    with open(output_path, encoding="utf-8") as f:
        contexts = json.load(f)

    with_meds = sum(1 for c in contexts if c.get("current_medications"))
    with_diag = sum(1 for c in contexts if c.get("diagnoses"))
    with_labs = sum(1 for c in contexts if c.get("labs"))
    with_notes = sum(1 for c in contexts if c.get("chief_complaint"))
    ages = [c["age"] for c in contexts if c.get("age") is not None]
    print(f"Created {len(contexts)} MIMIC-III patient contexts → {output_path.relative_to(PROJECT_ROOT)}")
    if ages:
        print(f"  - Ages: {min(ages)}~{max(ages)}")
    print(f"  - With medications: {with_meds}")
    print(f"  - With diagnoses: {with_diag}")
    print(f"  - With labs: {with_labs}")
    print(f"  - With clinical notes: {with_notes}")
    print(f"  - Female: {sum(1 for c in contexts if c.get('gender') == 'F')}, "
          f"Male: {sum(1 for c in contexts if c.get('gender') == 'M')}")


if __name__ == "__main__":
    generate_review_cases()
    generate_clarify_cases()
    generate_consult_case()
    raw_dir = resolve_mimic_raw_dir()
    use_notes = raw_dir is not None and is_full_mimic_dataset(raw_dir)
    if raw_dir:
        tier = "full 1.4" if use_notes else "demo/partial"
        print(f"MIMIC source: {raw_dir.relative_to(PROJECT_ROOT)} ({tier})")
    # Demo fixture generation uses a small sample; full build: python -m src.cli build-mimic
    generate_mimic_patient_contexts(max_samples=500 if use_notes else 2000, skip_notes=not use_notes)
    print("\nAll case templates and MIMIC patient contexts generated successfully.")
