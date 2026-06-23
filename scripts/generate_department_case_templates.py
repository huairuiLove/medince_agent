#!/usr/bin/env python3
"""Generate one clinical case template per department in catalog.json."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.case_templates import departments_missing_templates, list_case_templates
from src.config import datasets_path
from src.utils import load_json, save_json

OUTPUT = datasets_path("case_templates/department_templates.json")

# dept_id -> (title, description, age, gender, current_meds, candidate)
DEPT_SCENARIOS: dict[str, tuple[str, str, int, str, list[dict], dict]] = {
    "respiratory": (
        "COPD 急性加重抗感染",
        "慢阻肺急性加重，长期吸入激素基础上加用大环内酯",
        68,
        "M",
        [{"name": "salbutamol", "dose": "2 puff prn"}, {"name": "budesonide", "dose": "400mcg bid"}],
        {"name": "azithromycin", "dose": "500mg", "indication": "COPD 急性加重"},
    ),
    "neurology": (
        "抗癫痫药物加用",
        "癫痫患者丙戊酸基础上加用拉莫三嗪",
        28,
        "F",
        [{"name": "valproate", "dose": "500mg bid"}],
        {"name": "lamotrigine", "dose": "25mg", "indication": "癫痫"},
    ),
    "neurosurgery": (
        "围术期抗凝桥接",
        "颅脑肿瘤术前，华法林需桥接低分子肝素",
        55,
        "M",
        [{"name": "warfarin", "dose": "5mg"}, {"name": "levetiracetam", "dose": "500mg bid"}],
        {"name": "enoxaparin", "dose": "40mg", "indication": "术前抗凝桥接"},
    ),
    "radiology": (
        "造影前二甲双胍暂停",
        "糖尿病拟行 CT 增强，需评估二甲双胍",
        62,
        "F",
        [{"name": "metformin", "dose": "850mg bid"}, {"name": "lisinopril", "dose": "10mg"}],
        {"name": "iohexol", "dose": "350mgI/ml", "indication": "CT 增强造影"},
    ),
    "cardiology": (
        "心衰多药联用审查",
        "心衰+房颤+CKD，新增胺碘酮",
        72,
        "M",
        [
            {"name": "digoxin", "dose": "0.125mg"},
            {"name": "furosemide", "dose": "40mg"},
            {"name": "warfarin", "dose": "3mg"},
            {"name": "spironolactone", "dose": "20mg"},
        ],
        {"name": "amiodarone", "dose": "200mg", "indication": "房颤节律控制"},
    ),
    "gastroenterology": (
        "PPI 与氯吡格雷",
        "消化性溃疡史，双抗基础上加 PPI",
        58,
        "M",
        [{"name": "aspirin", "dose": "100mg"}, {"name": "clopidogrel", "dose": "75mg"}],
        {"name": "omeprazole", "dose": "20mg", "indication": "溃疡预防"},
    ),
    "oncology": (
        "化疗 DDI 审查",
        "顺铂方案联用强 CYP3A4 抑制剂",
        58,
        "M",
        [{"name": "cisplatin", "dose": "75mg/m2"}],
        {"name": "ketoconazole", "dose": "200mg", "indication": "真菌预防"},
    ),
    "emergency": (
        "急诊阿片+苯二氮卓",
        "急性创伤镇痛，吗啡联用地西泮",
        45,
        "M",
        [],
        {"name": "morphine", "dose": "5mg IV", "indication": "急性疼痛"},
    ),
    "pharmacy": (
        "高警示药品审查",
        "临床药师会诊：华法林+NSAIDs 出血风险",
        67,
        "M",
        [{"name": "warfarin", "dose": "5mg"}, {"name": "aspirin", "dose": "81mg"}],
        {"name": "ibuprofen", "dose": "400mg", "indication": "止痛"},
    ),
    "general_internal": (
        "高血压联合用药",
        "普通内科住院，CCB 基础上加 ACEI",
        55,
        "M",
        [{"name": "amlodipine", "dose": "5mg"}],
        {"name": "lisinopril", "dose": "10mg", "indication": "高血压"},
    ),
    "nephrology": (
        "CKD 高钾风险",
        "CKD4 期，ACEI+螺内酯联用",
        64,
        "F",
        [{"name": "lisinopril", "dose": "10mg"}, {"name": "furosemide", "dose": "40mg"}],
        {"name": "spironolactone", "dose": "25mg", "indication": "蛋白尿"},
    ),
    "endocrinology": (
        "糖尿病二甲双胍审查",
        "2 型糖尿病，eGFR 偏低评估二甲双胍",
        58,
        "F",
        [{"name": "glibenclamide", "dose": "5mg"}],
        {"name": "metformin", "dose": "850mg bid", "indication": "2 型糖尿病"},
    ),
    "hematology": (
        "抗凝+抗血小板",
        "血液科患者华法林基础上加氯吡格雷",
        60,
        "M",
        [{"name": "warfarin", "dose": "5mg"}],
        {"name": "clopidogrel", "dose": "75mg", "indication": "血小板减少症相关"},
    ),
    "geriatrics": (
        "老年多重用药",
        "80 岁多病共存，新增苯二氮卓",
        80,
        "F",
        [
            {"name": "metoprolol", "dose": "25mg"},
            {"name": "amlodipine", "dose": "5mg"},
            {"name": "donepezil", "dose": "5mg"},
        ],
        {"name": "lorazepam", "dose": "0.5mg", "indication": "失眠"},
    ),
    "rheumatology": (
        "MTX 与 NSAIDs",
        "类风湿关节炎，MTX 基础上加布洛芬",
        52,
        "F",
        [{"name": "methotrexate", "dose": "15mg weekly"}, {"name": "folic acid", "dose": "5mg"}],
        {"name": "ibuprofen", "dose": "400mg", "indication": "关节痛"},
    ),
    "infectious_disease": (
        "抗感染过敏史缺失",
        "社区肺炎，阿莫西林候选，过敏史未知",
        34,
        "F",
        [],
        {"name": "amoxicillin", "dose": "500mg tid", "indication": "社区获得性肺炎"},
    ),
    "obstetrics_gynecology": (
        "妊娠期高血压",
        "妊娠 32 周，新增甲基多巴",
        28,
        "F",
        [{"name": "folic acid", "dose": "5mg"}],
        {"name": "methyldopa", "dose": "250mg bid", "indication": "妊娠期高血压"},
    ),
    "pediatrics": (
        "儿童抗生素选择",
        "8 岁儿童急性中耳炎",
        8,
        "M",
        [],
        {"name": "amoxicillin", "dose": "25mg/kg bid", "indication": "急性中耳炎"},
    ),
    "orthopedic": (
        "围术期 NSAIDs",
        "骨科术后，华法林基础上加布洛芬",
        70,
        "M",
        [{"name": "warfarin", "dose": "3mg"}],
        {"name": "ibuprofen", "dose": "400mg", "indication": "术后止痛"},
    ),
    "urology": (
        "α 阻滞剂+降压",
        "良性前列腺增生，坦索罗辛+多沙唑嗪",
        65,
        "M",
        [{"name": "tamsulosin", "dose": "0.4mg"}],
        {"name": "doxazosin", "dose": "2mg", "indication": "BPH"},
    ),
    "icu": (
        "ICU 镇静镇痛",
        "机械通气患者，丙泊酚+芬太尼",
        48,
        "M",
        [{"name": "norepinephrine", "dose": "0.1mcg/kg/min"}, {"name": "vancomycin", "dose": "1g"}],
        {"name": "propofol", "dose": "50mg/h", "indication": "镇静"},
    ),
    "anesthesiology": (
        "麻醉诱导用药",
        "全麻诱导，咪达唑仑+芬太尼",
        50,
        "F",
        [{"name": "ondansetron", "dose": "4mg"}],
        {"name": "midazolam", "dose": "2mg IV", "indication": "麻醉诱导"},
    ),
    "psychiatry": (
        "SSRI+苯二氮卓",
        "抑郁焦虑共病，舍曲林+劳拉西泮",
        35,
        "F",
        [{"name": "sertraline", "dose": "50mg"}],
        {"name": "lorazepam", "dose": "0.5mg", "indication": "焦虑"},
    ),
    "dermatology": (
        "系统免疫抑制",
        "银屑病，甲氨蝶呤基础上加酮康唑",
        42,
        "M",
        [{"name": "methotrexate", "dose": "15mg weekly"}],
        {"name": "ketoconazole", "dose": "200mg", "indication": "真菌感染"},
    ),
    "ophthalmology": (
        "青光眼系统用药",
        "开角型青光眼，噻吗洛尔滴眼液+口服 β 阻滞剂",
        60,
        "M",
        [{"name": "timolol", "dose": "0.5% eye drops bid"}],
        {"name": "metoprolol", "dose": "25mg", "indication": "高血压"},
    ),
    "ent": (
        "急性咽炎抗感染",
        "急性咽炎，阿莫西林候选",
        26,
        "F",
        [],
        {"name": "amoxicillin", "dose": "500mg tid", "indication": "急性咽炎"},
    ),
    "rehabilitation": (
        "康复期多重用药",
        "卒中后康复，多种心血管药物联用",
        72,
        "M",
        [
            {"name": "aspirin", "dose": "100mg"},
            {"name": "atorvastatin", "dose": "20mg"},
            {"name": "metoprolol", "dose": "25mg"},
        ],
        {"name": "clopidogrel", "dose": "75mg", "indication": "卒中二级预防"},
    ),
}


def build_cases() -> list[dict]:
    catalog = load_json(datasets_path("departments/catalog.json"))
    dept_ids = [item["dept_id"] for item in catalog.get("departments", []) if item.get("dept_id")]
    missing = [dept for dept in dept_ids if dept not in DEPT_SCENARIOS]
    if missing:
        raise SystemExit(f"Missing scenario definitions for: {', '.join(missing)}")

    cases: list[dict] = []
    for dept_id in dept_ids:
        title, description, age, gender, current_meds, candidate = DEPT_SCENARIOS[dept_id]
        pregnancy = "pregnant" if dept_id == "obstetrics_gynecology" else "not_applicable"
        cases.append(
            {
                "id": f"dept_{dept_id}_01",
                "title": title,
                "description": description,
                "department": dept_id,
                "category": dept_id,
                "request": {
                    "patient_context": {
                        "age": age,
                        "gender": gender,
                        "department": dept_id,
                        "pregnancy_status": pregnancy,
                        "current_medications": current_meds,
                        "allergies": [],
                        "diagnoses": [],
                    },
                    "candidate_drugs": [candidate],
                },
            }
        )
    return cases


def main() -> None:
    payload = {
        "description": "各科室默认病例模板 — 每个科室至少 1 个",
        "cases": build_cases(),
    }
    save_json(payload, OUTPUT)
    print(f"Wrote {len(payload['cases'])} department templates to {OUTPUT}")

    missing = departments_missing_templates()
    if missing:
        raise SystemExit(f"Departments still missing templates: {', '.join(missing)}")
    print(f"Coverage OK: {len(list_case_templates())} templates total")


if __name__ == "__main__":
    main()
