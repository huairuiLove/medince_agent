"""Load department review_config, core_formulary, and agent strategy from catalog."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.config import datasets_path
from src.department.formulary import DepartmentFormularyFilter
from src.utils import load_json

REVIEW_CONFIGS_PATH = datasets_path("departments/dept_review_configs.json")
CATALOG_PATH = datasets_path("departments/catalog.json")

_DEFAULT_REVIEW_CONFIG: dict[str, Any] = {
    "default_strict": True,
    "priority_categories": ["drug_interaction", "duplicate_ingredient"],
    "auto_enable_agents": ["clinical_pharmacist", "internal_medicine", "allergy_specialist"],
    "conditional_agents": {},
    "lab_context_defaults": [],
    "formulary_scope": "general_formulary",
    "common_indications": [],
}

_DEPT_OVERRIDES: dict[str, dict[str, Any]] = {
    "cardiology": {
        "priority_categories": ["drug_interaction", "duplicate_ingredient", "special_population"],
        "auto_enable_agents": ["clinical_pharmacist", "internal_medicine", "allergy_specialist"],
        "conditional_agents": {"cardiology_specialist": {"always": True}},
        "lab_context_defaults": ["INR", "eGFR", "血钾", "QTc", "BNP"],
        "formulary_scope": "cardiology_formulary",
        "common_indications": ["心力衰竭", "房颤", "冠心病", "高血压", "高脂血症"],
    },
    "neurology": {
        "lab_context_defaults": ["eGFR", "血钠", "INR"],
        "conditional_agents": {"neurology_specialist": {"always": True}},
        "common_indications": ["癫痫", "帕金森病", "卒中二级预防", "偏头痛"],
    },
    "oncology": {
        "priority_categories": ["drug_interaction", "special_population", "allergy"],
        "conditional_agents": {"oncology_specialist": {"always": True}},
        "common_indications": ["实体瘤", "血液肿瘤", "化疗支持治疗"],
    },
    "pediatrics": {
        "conditional_agents": {"pediatrics_specialist": {"always": True}},
        "lab_context_defaults": ["体重", "eGFR", "肝功能"],
        "common_indications": ["儿童感染", "哮喘", "癫痫", "发热"],
    },
    "obstetrics_gynecology": {
        "conditional_agents": {"obgyn_specialist": {"always": True}},
        "lab_context_defaults": ["hCG", "eGFR", "血压"],
        "common_indications": ["妊娠期高血压", "先兆早产", "辅助生殖"],
    },
    "icu": {
        "conditional_agents": {"icu_specialist": {"always": True}},
        "lab_context_defaults": ["eGFR", "乳酸", "INR", "血钾", "动脉血气"],
        "common_indications": ["脓毒症", "休克", "呼吸衰竭", "镇静镇痛"],
    },
    "respiratory": {
        "lab_context_defaults": ["血氧", "血气", "嗜酸性粒细胞"],
        "common_indications": ["COPD", "哮喘", "肺炎", "肺栓塞"],
    },
    "nephrology": {
        "lab_context_defaults": ["eGFR", "血钾", "血磷", "iPTH"],
        "common_indications": ["CKD", "透析", "肾性高血压", "高钾血症"],
    },
    "endocrinology": {
        "lab_context_defaults": ["HbA1c", "血糖", "TSH", "eGFR"],
        "common_indications": ["糖尿病", "甲状腺疾病", "骨质疏松"],
    },
    "geriatrics": {
        "lab_context_defaults": ["eGFR", "INR", "血钠"],
        "common_indications": ["多病共存", "跌倒风险", "认知障碍", " polypharmacy"],
    },
    "emergency": {
        "priority_categories": ["drug_interaction", "allergy", "special_population"],
        "common_indications": ["急性中毒", "过敏性休克", "急性冠脉综合征"],
    },
    "pharmacy": {
        "auto_enable_agents": ["clinical_pharmacist", "pharmacy_inventory"],
        "common_indications": ["全院用药审查", "高警示药品", "库存替代"],
    },
}

_CORE_FORMULARY: dict[str, list[str]] = {
    "cardiology": [
        "warfarin", "rivaroxaban", "apixaban", "dabigatran",
        "metoprolol", "bisoprolol", "carvedilol",
        "lisinopril", "enalapril", "valsartan", "losartan",
        "atorvastatin", "rosuvastatin",
        "amiodarone", "sotalol", "dronedarone",
        "digoxin", "furosemide", "spironolactone",
        "aspirin", "clopidogrel", "ticagrelor",
        "nitroglycerin", "isosorbide", "sildenafil",
    ],
    "neurology": [
        "levetiracetam", "valproate", "carbamazepine", "lamotrigine",
        "phenytoin", "levodopa", "pramipexole", "ropinirole",
        "aspirin", "clopidogrel", "warfarin", "rivaroxaban",
        "metoprolol", "amlodipine", "atorvastatin",
    ],
    "respiratory": [
        "salbutamol", "ipratropium", "tiotropium", "fluticasone",
        "budesonide", "montelukast", "theophylline",
        "prednisone", "azithromycin", "levofloxacin",
        "heparin", "enoxaparin", "oxygen",
    ],
    "oncology": [
        "cisplatin", "carboplatin", "paclitaxel", "doxorubicin",
        "cyclophosphamide", "methotrexate", "imatinib",
        "ondansetron", "dexamethasone", "filgrastim",
        "morphine", "fentanyl", "paracetamol",
    ],
    "icu": [
        "norepinephrine", "epinephrine", "vasopressin", "dopamine",
        "midazolam", "propofol", "fentanyl", "morphine",
        "vancomycin", "meropenem", "piperacillin",
        "heparin", "furosemide", "insulin",
    ],
    "pediatrics": [
        "amoxicillin", "azithromycin", "ceftriaxone",
        "salbutamol", "budesonide", "paracetamol", "ibuprofen",
        "valproate", "levetiracetam", "prednisolone",
    ],
    "obstetrics_gynecology": [
        "oxytocin", "misoprostol", "magnesium sulfate",
        "labetalol", "nifedipine", "methyldopa",
        "folic acid", "iron", "levothyroxine",
    ],
    "emergency": [
        "epinephrine", "naloxone", "flumazenil", "acetylcysteine",
        "diphenhydramine", "methylprednisolone", "adrenaline",
        "morphine", "fentanyl", "midazolam",
    ],
    "nephrology": [
        "furosemide", "spironolactone", "lisinopril", "valsartan",
        "sevelamer", "calcitriol", "erythropoietin",
        "warfarin", "heparin", "insulin",
    ],
    "gastroenterology": [
        "omeprazole", "pantoprazole", "mesalazine", "infliximab",
        "lactulose", "rifaximin", "ursodeoxycholic acid",
    ],
    "psychiatry": [
        "sertraline", "fluoxetine", "escitalopram", "venlafaxine",
        "quetiapine", "olanzapine", "risperidone", "lithium",
        "valproate", "lorazepam",
    ],
    "infectious_disease": [
        "vancomycin", "meropenem", "piperacillin", "tazobactam",
        "linezolid", "daptomycin", "fluconazole", "acyclovir",
    ],
    "hematology": [
        "warfarin", "heparin", "enoxaparin", "aspirin",
        "hydroxyurea", "imatinib", "rituximab",
    ],
    "geriatrics": [
        "metoprolol", "amlodipine", "lisinopril", "furosemide",
        "aspirin", "clopidogrel", "warfarin", "donepezil",
        "paracetamol", "tramadol",
    ],
    "pharmacy": [
        "warfarin", "heparin", "insulin", "morphine",
        "vancomycin", "amiodarone", "methotrexate",
    ],
}


def _load_supplemental_configs() -> dict[str, dict[str, Any]]:
    path = REVIEW_CONFIGS_PATH
    if path.exists():
        data = load_json(path)
        return data.get("departments", data) if isinstance(data, dict) else {}
    return {}


def _merge_review_config(dept_id: str, supplemental: dict[str, Any]) -> dict[str, Any]:
    merged = dict(_DEFAULT_REVIEW_CONFIG)
    merged.update(_DEPT_OVERRIDES.get(dept_id, {}))
    extra = supplemental.get("review_config") or supplemental.get("review_config", {})
    if isinstance(extra, dict):
        merged.update(extra)
    merged["formulary_scope"] = merged.get("formulary_scope") or f"{dept_id}_formulary"
    return merged


def _resolve_core_formulary(dept_id: str, supplemental: dict[str, Any]) -> list[str]:
    if supplemental.get("core_formulary"):
        return list(supplemental["core_formulary"])
    if dept_id in _CORE_FORMULARY:
        return list(_CORE_FORMULARY[dept_id])
    return []


@dataclass
class DepartmentContext:
    dept_id: str
    name_cn: str = ""
    name_en: str = ""
    description: str = ""
    review_config: dict[str, Any] = field(default_factory=dict)
    core_formulary: list[str] = field(default_factory=list)
    nav_routes: list[str] = field(default_factory=list)

    @property
    def formulary_filter(self) -> DepartmentFormularyFilter:
        return DepartmentFormularyFilter(self.core_formulary)

    @property
    def priority_categories(self) -> list[str]:
        return list(self.review_config.get("priority_categories") or [])

    @property
    def lab_context_defaults(self) -> list[str]:
        return list(self.review_config.get("lab_context_defaults") or [])

    @property
    def common_indications(self) -> list[str]:
        return list(self.review_config.get("common_indications") or [])

    @property
    def auto_enable_agents(self) -> list[str]:
        return list(self.review_config.get("auto_enable_agents") or [])

    @property
    def department_agent_ids(self) -> list[str]:
        conditional = self.review_config.get("conditional_agents") or {}
        return list(conditional.keys())

    def to_dict(self) -> dict[str, Any]:
        return {
            "dept_id": self.dept_id,
            "name_cn": self.name_cn,
            "name_en": self.name_en,
            "description": self.description,
            "review_config": self.review_config,
            "core_formulary": self.core_formulary,
            "nav_routes": self.nav_routes,
        }


def _load_catalog_specs() -> dict[str, dict[str, Any]]:
    data = load_json(CATALOG_PATH)
    return {item["dept_id"]: item for item in data.get("departments", [])}


@lru_cache(maxsize=1)
def _catalog_and_supplemental() -> tuple[dict[str, dict[str, Any]], dict]:
    catalog = _load_catalog_specs()
    supplemental = _load_supplemental_configs()
    return catalog, supplemental


@lru_cache(maxsize=64)
def get_department_context(dept_id: str) -> DepartmentContext | None:
    dept_id = (dept_id or "").strip()
    if not dept_id:
        return None

    catalog, supplemental_all = _catalog_and_supplemental()
    spec = catalog.get(dept_id)
    supplemental = supplemental_all.get(dept_id, {})

    if spec is None and dept_id not in _DEPT_OVERRIDES and dept_id not in supplemental_all:
        return None

    review_config = _merge_review_config(dept_id, supplemental)
    core_formulary = _resolve_core_formulary(dept_id, supplemental)

    return DepartmentContext(
        dept_id=dept_id,
        name_cn=spec.get("name_cn", supplemental.get("name_cn", dept_id)) if spec else supplemental.get("name_cn", dept_id),
        name_en=spec.get("name_en", "") if spec else supplemental.get("name_en", ""),
        description=spec.get("description", "") if spec else supplemental.get("description", ""),
        review_config=review_config,
        core_formulary=core_formulary,
        nav_routes=list(spec.get("nav_routes") or supplemental.get("nav_routes") or []) if spec else list(supplemental.get("nav_routes") or []),
    )


def clear_department_context_cache() -> None:
    _catalog_and_supplemental.cache_clear()
    get_department_context.cache_clear()
