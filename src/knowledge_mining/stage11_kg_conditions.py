"""Stage 11 Condition nodes for department-related diseases."""

from __future__ import annotations

from typing import Any

STAGE11_CONDITIONS: list[dict[str, Any]] = [
    {"id": "cond_heart_failure", "type": "Condition", "name": "心力衰竭", "department": "cardiology"},
    {"id": "cond_acs", "type": "Condition", "name": "急性冠脉综合征", "department": "cardiology"},
    {"id": "cond_ckd", "type": "Condition", "name": "慢性肾病", "department": "nephrology"},
    {"id": "cond_epilepsy", "type": "Condition", "name": "癫痫", "department": "neurology"},
    {"id": "cond_parkinson", "type": "Condition", "name": "帕金森病", "department": "neurology"},
    {"id": "cond_ra", "type": "Condition", "name": "类风湿关节炎", "department": "rheumatology"},
    {"id": "cond_sle", "type": "Condition", "name": "系统性红斑狼疮", "department": "rheumatology"},
    {"id": "cond_leukemia", "type": "Condition", "name": "急性白血病", "department": "hematology"},
    {"id": "cond_cirrhosis", "type": "Condition", "name": "肝硬化", "department": "gastroenterology"},
    {"id": "cond_ibd", "type": "Condition", "name": "炎症性肠病", "department": "gastroenterology"},
    {"id": "cond_sepsis", "type": "Condition", "name": "败血症", "department": "icu"},
    {"id": "cond_hiv", "type": "Condition", "name": "HIV/AIDS", "department": "infectious_disease"},
    {"id": "cond_depression", "type": "Condition", "name": "抑郁症", "department": "psychiatry"},
    {"id": "cond_schizophrenia", "type": "Condition", "name": "精神分裂症", "department": "psychiatry"},
    {"id": "cond_hyperthyroid", "type": "Condition", "name": "甲状腺功能亢进", "department": "endocrinology"},
    {"id": "cond_osteoporosis", "type": "Condition", "name": "骨质疏松", "department": "endocrinology"},
    {"id": "cond_bph", "type": "Condition", "name": "前列腺增生", "department": "urology"},
    {"id": "cond_glaucoma", "type": "Condition", "name": "青光眼", "department": "ophthalmology"},
    {"id": "cond_psoriasis", "type": "Condition", "name": "银屑病", "department": "dermatology"},
    {"id": "cond_copd", "type": "Condition", "name": "COPD", "department": "respiratory"},
    {"id": "cond_asthma", "type": "Condition", "name": "哮喘", "department": "respiratory"},
    {"id": "cond_pneumonia", "type": "Condition", "name": "社区获得性肺炎", "department": "respiratory"},
    {"id": "cond_preterm", "type": "Condition", "name": "先兆早产", "department": "obstetrics_gynecology"},
    {"id": "cond_glioma", "type": "Condition", "name": "胶质瘤", "department": "neurosurgery"},
    {"id": "cond_fracture", "type": "Condition", "name": "骨折", "department": "orthopedic"},
]


def merge_condition_nodes(kg: dict[str, Any]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = list(kg.get("nodes", []))
    existing = {node["id"] for node in nodes}
    added = 0
    for cond in STAGE11_CONDITIONS:
        if cond["id"] in existing:
            continue
        nodes.append(dict(cond))
        existing.add(cond["id"])
        added += 1
    meta = dict(kg.get("meta") or {})
    meta["stage11_conditions_added"] = added
    return {**kg, "nodes": nodes, "meta": meta}
