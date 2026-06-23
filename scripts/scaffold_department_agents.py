#!/usr/bin/env python3
"""Scaffold department specialist agents for all catalog departments."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import datasets_path

AGENTS_ROOT = datasets_path("agents")
REGISTRY_PATH = AGENTS_ROOT / "registry.yaml"

# agent_id -> spec (departments must match catalog.json dept_id)
NEW_DEPARTMENT_AGENTS: dict[str, dict] = {
    "respiratory_specialist": {
        "agent_name": "呼吸专科",
        "role": "COPD/哮喘/肺炎抗感染与吸入治疗审查",
        "departments": ["respiratory"],
        "drug_keywords": ["theophylline", "azithromycin", "salbutamol", "budesonide", "montelukast"],
        "skills": {
            "base": "你是 {{department}} 专科审查智能体，聚焦 COPD、哮喘、肺炎与吸入/全身激素用药安全。",
            "copd_management": "审查 ICS/LABA/LAMA 联合；急性加重时抗生素选择与茶碱/CYP1A2 交互。",
            "inhaled_therapy": "关注吸入糖皮质激素与强 CYP3A4 抑制剂联用时的全身暴露。",
            "respiratory_antibiotic": "社区/医院获得性肺炎抗菌谱、QT 延长与过敏风险。",
        },
    },
    "neurosurgery_specialist": {
        "agent_name": "神经外科专科",
        "role": "颅脑围术期抗凝、颅内压与癫痫预防用药审查",
        "departments": ["neurosurgery"],
        "drug_keywords": ["levetiracetam", "dexamethasone", "phenytoin", "mannitol"],
        "skills": {
            "base": "你是 {{department}} 专科审查智能体，聚焦颅脑肿瘤/血肿围术期用药与抗凝桥接。",
            "perioperative_anticoag": "术前华法林/DOAC 桥接、术后 VTE 预防与再出血风险平衡。",
            "intracranial_htn": "地塞米松、甘露醇与电解质/血糖监测。",
            "seizure_prophylaxis": "围术期抗癫痫药选择与丙戊酸/苯妥英浓度监测。",
        },
    },
    "radiology_specialist": {
        "agent_name": "放射专科",
        "role": "造影剂安全、二甲双胍暂停与过敏预处理审查",
        "departments": ["radiology"],
        "drug_keywords": ["iohexol", "iodixanol", "gadolinium", "metformin"],
        "skills": {
            "base": "你是 {{department}} 专科审查智能体，聚焦影像检查相关用药与造影剂安全。",
            "contrast_safety": "碘造影剂过敏史、肾功能与 eGFR 阈值；钆剂 NSF 风险。",
            "metformin_hold": "增强 CT 前后二甲双胍暂停/恢复时机与乳酸酸中毒风险。",
            "allergy_premedication": "既往造影剂反应时的预处理方案与 β 阻滞剂/哮喘交互。",
        },
    },
    "gastroenterology_specialist": {
        "agent_name": "消化专科",
        "role": "PPI/抗血小板、IBD 免疫抑制与肝代谢用药审查",
        "departments": ["gastroenterology"],
        "drug_keywords": ["omeprazole", "pantoprazole", "infliximab", "mesalazine"],
        "skills": {
            "base": "你是 {{department}} 专科审查智能体，聚焦消化性溃疡、IBD 与肝病相关用药。",
            "ppi_antiplatelet": "PPI 与氯吡格雷 CYP2C19 交互；双抗+PPI 的 GI 保护。",
            "ibd_immunosuppress": "生物制剂/硫嘌呤与感染、TB 筛查及疫苗接种。",
            "hepatic_metabolism": "Child-Pugh 分级下剂量调整；对乙酰氨基酚肝毒性上限。",
        },
    },
    "emergency_specialist": {
        "agent_name": "急诊专科",
        "role": "急性中毒、复苏用药与急诊镇痛镇静审查",
        "departments": ["emergency"],
        "drug_keywords": ["naloxone", "epinephrine", "morphine", "midazolam", "flumazenil"],
        "skills": {
            "base": "你是 {{department}} 专科审查智能体，聚焦急诊快速决策与高危急性用药。",
            "acute_toxicology": "对乙酰氨基酚 NAC、阿片/苯二氮䓬拮抗剂滴定与再中毒。",
            "resuscitation_drugs": "肾上腺素与 β 阻滞剂、钙剂与洋地黄中毒交互。",
            "analgesia_sedation": "阿片+苯二氮䓬呼吸抑制；创伤/休克下镇痛选择。",
        },
    },
    "pharmacy_specialist": {
        "agent_name": "药学专科",
        "role": "高警示药品、全院 DDI 与 formulary 一致性审查",
        "departments": ["pharmacy"],
        "drug_keywords": ["warfarin", "insulin", "methotrexate", "morphine", "amiodarone"],
        "skills": {
            "base": "你是 {{department}} 专科审查智能体，聚焦全院用药安全与高警示药品管理。",
            "high_alert_review": "抗凝、胰岛素、化疗、阿片类等高警示药品双重核对。",
            "formulary_alignment": "院内外购药与 formulary 偏差、替代方案与库存。",
            "pharmacy_ddi": "跨科室复杂 DDI 与剂量/途径/频次合理性。",
        },
    },
    "general_internal_specialist": {
        "agent_name": "普内专科",
        "role": "住院多病共存、慢病联合用药与 off-label 风险审查",
        "departments": ["general_internal"],
        "drug_keywords": ["amlodipine", "lisinopril", "metformin", "atorvastatin"],
        "skills": {
            "base": "你是 {{department}} 专科审查智能体，聚焦普通内科住院患者常规用药安全。",
            "polypharmacy": "≥5 种药物时重复成分、抗胆碱负荷与肾排泄叠加。",
            "chronic_disease_combo": "高血压/糖尿病/高脂血症三联与 eGFR 相关调整。",
            "comorbidity_risk": "合并 CKD、肝病、心衰时的剂量与禁忌。",
        },
    },
    "nephrology_specialist": {
        "agent_name": "肾内专科",
        "role": "肾剂量调整、高钾风险与透析用药审查",
        "departments": ["nephrology"],
        "drug_keywords": ["furosemide", "spironolactone", "sevelamer", "calcitriol"],
        "skills": {
            "base": "你是 {{department}} 专科审查智能体，聚焦 CKD/透析患者用药与电解质安全。",
            "renal_dose_adjust": "按 eGFR 分级调整 DOAC、氨基糖苷、加巴喷丁等。",
            "hyperkalemia_risk": "ACEI/ARB+螺内酯+保钾利尿剂；RAAS 双重阻断。",
            "dialysis_medication": "透析日给药时机、肾排泄药物与造影剂肾病预防。",
        },
    },
    "endocrinology_specialist": {
        "agent_name": "内分泌专科",
        "role": "糖尿病多药联合、甲状腺与激素替代审查",
        "departments": ["endocrinology"],
        "drug_keywords": ["metformin", "glibenclamide", "levothyroxine", "insulin"],
        "skills": {
            "base": "你是 {{department}} 专科审查智能体，聚焦糖尿病、甲状腺与肾上腺用药。",
            "diabetes_combo": "磺脲+磺脲重复、胰岛素+磺脲低血糖、SGLT2+利尿剂脱水。",
            "thyroid_ddi": "左甲状腺素与铁/钙/ PPI 吸收间隔；胺碘酮致甲功异常。",
            "steroid_management": "应激剂量激素、库欣与降糖方案调整。",
        },
    },
    "geriatrics_specialist": {
        "agent_name": "老年专科",
        "role": "Beers 准则、跌倒风险与去处方化审查",
        "departments": ["geriatrics"],
        "drug_keywords": ["lorazepam", "diphenhydramine", "glyburide", "tramadol"],
        "skills": {
            "base": "你是 {{department}} 专科审查智能体，聚焦老年多病共存与 Beers 准则。",
            "beers_criteria": "苯二氮䓬、抗胆碱能药、长效磺脲、第一代抗组胺禁忌。",
            "fall_risk": "镇静/降压/α 阻滞剂叠加致体位性低血压与跌倒。",
            "deprescribing": "冗余 PPI、苯二氮䓬与 duplicate 成分的去处方建议。",
        },
    },
    "rheumatology_specialist": {
        "agent_name": "风湿专科",
        "role": "MTX/生物制剂、NSAIDs 与免疫抑制审查",
        "departments": ["rheumatology"],
        "drug_keywords": ["methotrexate", "leflunomide", "infliximab", "adalimumab"],
        "skills": {
            "base": "你是 {{department}} 专科审查智能体，聚焦 RA/SLE/痛风等风湿免疫用药。",
            "mtx_monitoring": "MTX+NSAIDs/甲氧苄啶致毒性；叶酸与 LFT 监测。",
            "biologic_infection": "TNF 抑制剂与活动性感染/TB；活疫苗禁忌。",
            "nsaid_gi_risk": "NSAIDs+抗凝/激素的 GI 出血；肾毒性叠加。",
        },
    },
    "infectious_disease_specialist": {
        "agent_name": "感染专科",
        "role": "抗感染谱系、耐药管理与 HIV/TB/真菌 DDI 审查",
        "departments": ["infectious_disease"],
        "drug_keywords": ["vancomycin", "meropenem", "linezolid", "fluconazole"],
        "skills": {
            "base": "你是 {{department}} 专科审查智能体，聚焦抗感染选择与 stewardship。",
            "antibiotic_spectrum": "经验/目标治疗谱系、过敏史与交叉过敏。",
            "resistance_stewardship": "碳青霉烯/万古霉素/利奈唑胺使用指征与 TDM。",
            "hiv_tb_antifungal": "抗结核/HIV/抗真菌与 CYP 强抑制剂/诱导剂交互。",
        },
    },
    "orthopedic_specialist": {
        "agent_name": "骨科专科",
        "role": "围术期抗凝、NSAIDs 与 VTE 预防审查",
        "departments": ["orthopedic"],
        "drug_keywords": ["ibuprofen", "enoxaparin", "warfarin", "celecoxib"],
        "skills": {
            "base": "你是 {{department}} 专科审查智能体，聚焦骨科围术期镇痛与血栓预防。",
            "perioperative_anticoag": "关节置换/脊柱手术抗凝桥接与出血平衡。",
            "nsaid_bone_healing": "NSAIDs 对骨愈合影响；华法林+NSAIDs 出血。",
            "vte_prophylaxis": "LMWH/DOAC 剂量与肾功能、硬膜外麻醉禁忌。",
        },
    },
    "urology_specialist": {
        "agent_name": "泌尿专科",
        "role": "α 阻滞剂低血压、BPH 与抗凝联用审查",
        "departments": ["urology"],
        "drug_keywords": ["tamsulosin", "finasteride", "doxazosin", "sildenafil"],
        "skills": {
            "base": "你是 {{department}} 专科审查智能体，聚焦泌尿系疾病与相关用药。",
            "alpha_blocker_hypotension": "多种 α 阻滞剂叠加；与 PDE5 抑制剂低血压。",
            "anticoag_prostate": "前列腺手术/活检围术期抗凝管理。",
            "renal_stone_analgesia": "结石绞痛 NSAIDs/阿片与肾毒性药物。",
        },
    },
    "anesthesiology_specialist": {
        "agent_name": "麻醉专科",
        "role": "麻醉诱导、围术期抗凝与恶性高热用药审查",
        "departments": ["anesthesiology"],
        "drug_keywords": ["propofol", "midazolam", "succinylcholine", "sevoflurane"],
        "skills": {
            "base": "你是 {{department}} 专科审查智能体，聚焦围术期麻醉与镇痛用药。",
            "induction_agents": "诱导药+阿片/苯二氮䓬呼吸抑制；QT 延长叠加。",
            "anticoag_periop": "区域麻醉与抗凝/抗血小板时间窗。",
            "malignant_hyperthermia": "挥发性麻醉药/琥珀胆碱与 MH 易感；丹曲林准备。",
        },
    },
    "psychiatry_specialist": {
        "agent_name": "精神专科",
        "role": "五羟色胺综合征、QT 延长与精神药物 DDI 审查",
        "departments": ["psychiatry"],
        "drug_keywords": ["sertraline", "fluoxetine", "quetiapine", "lithium", "risperidone"],
        "skills": {
            "base": "你是 {{department}} 专科审查智能体，聚焦精神科药物安全与 DDI。",
            "serotonergic_syndrome": "SSRI+曲马多/MAOI/利奈唑胺/圣约翰草。",
            "qt_psychotropics": "抗精神病+大环内酯/氟喹诺酮 QT 延长风险。",
            "mood_stabilizer": "锂盐+NSAIDs/ACEI/利尿剂致锂中毒；丙戊酸交互。",
        },
    },
    "dermatology_specialist": {
        "agent_name": "皮肤专科",
        "role": "系统免疫抑制、维 A 酸致畸与外用/全身叠加审查",
        "departments": ["dermatology"],
        "drug_keywords": ["methotrexate", "acitretin", "cyclosporine", "isotretinoin"],
        "skills": {
            "base": "你是 {{department}} 专科审查智能体，聚焦皮肤病系统用药与外用药叠加。",
            "systemic_immunosuppress": "银屑病/天疱疮 MTX/环孢素与感染、肝毒性。",
            "retinoid_teratogenicity": "异维 A 酸/阿维 A 酯致畸与避孕要求。",
            "topical_systemic": "外用强效激素+系统激素；外用 β 阻滞剂+口服 β 阻滞剂。",
        },
    },
    "ophthalmology_specialist": {
        "agent_name": "眼科专科",
        "role": "眼毒性、青光眼局部/全身用药叠加审查",
        "departments": ["ophthalmology"],
        "drug_keywords": ["timolol", "latanoprost", "acetazolamide", "amiodarone"],
        "skills": {
            "base": "你是 {{department}} 专科审查智能体，聚焦眼内用药与全身药物眼毒性。",
            "ocular_toxicity": "胺碘酮/羟氯喹/他莫昔芬等药物性视网膜/角膜病变。",
            "topical_beta_blocker": "噻吗洛尔滴眼液+口服 β 阻滞剂致心动过缓。",
            "glaucoma_systemic": "碳酸酐酶抑制剂与磺胺过敏；前列腺素类叠加。",
        },
    },
    "ent_specialist": {
        "agent_name": "耳鼻喉专科",
        "role": "耳毒性、气道用药与头颈围术期审查",
        "departments": ["ent"],
        "drug_keywords": ["gentamicin", "amoxicillin", "dexamethasone", "pseudoephedrine"],
        "skills": {
            "base": "你是 {{department}} 专科审查智能体，聚焦头颈 ENT 专科用药。",
            "ototoxicity": "氨基糖苷/袢利尿剂耳毒性；听力监测。",
            "airway_sedation": "上气道手术镇静与反流入aspiration 风险。",
            "postop_analgesia": "头颈术后 NSAIDs/阿片与抗凝出血平衡。",
        },
    },
    "rehabilitation_specialist": {
        "agent_name": "康复专科",
        "role": "卒中二级预防、痉挛管理与长期多重用药审查",
        "departments": ["rehabilitation"],
        "drug_keywords": ["baclofen", "clopidogrel", "aspirin", "tizanidine"],
        "skills": {
            "base": "你是 {{department}} 专科审查智能体，聚焦神经康复与长期用药管理。",
            "stroke_secondary_prevention": "抗血小板/抗凝、他汀与 BP 目标；出血风险。",
            "spasticity_mgmt": "巴氯芬/替扎尼定与镇静、肝毒性叠加。",
            "long_term_polypharmacy": "康复期去处方化与功能相关药物优化。",
        },
    },
}


def write_skill_files(agent_id: str, skills: dict[str, str]) -> None:
    agent_dir = AGENTS_ROOT / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    for skill_id, body in skills.items():
        path = agent_dir / f"{skill_id}.md"
        path.write_text(body.strip() + "\n", encoding="utf-8")


def build_registry_entry(agent_id: str, spec: dict) -> dict:
    skill_ids = list(spec["skills"].keys())
    entry: dict = {
        "agent_id": agent_id,
        "agent_name": spec["agent_name"],
        "role": spec["role"],
        "module": "src.agents.department_specialist",
        "class": "DepartmentSpecialistAgent",
        "debate": True,
        "default_enabled": False,
        "skills": skill_ids,
        "activate_when": {"departments": spec["departments"]},
    }
    if spec.get("drug_keywords"):
        entry["activate_when"]["drug_keywords"] = spec["drug_keywords"]
    return entry


def update_registry(new_agents: dict[str, dict]) -> None:
    with REGISTRY_PATH.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    dept_agents = raw.setdefault("department_agents", {})
    added = 0
    for agent_id, spec in new_agents.items():
        if agent_id in dept_agents:
            continue
        dept_agents[agent_id] = build_registry_entry(agent_id, spec)
        added += 1
    with REGISTRY_PATH.open("w", encoding="utf-8") as fh:
        yaml.dump(raw, fh, allow_unicode=True, sort_keys=False, default_flow_style=False)
    print(f"Registry: added {added} department agents ({len(dept_agents)} total)")


def main() -> None:
    for agent_id, spec in NEW_DEPARTMENT_AGENTS.items():
        write_skill_files(agent_id, spec["skills"])
        print(f"Wrote skills for {agent_id}")
    update_registry(NEW_DEPARTMENT_AGENTS)


if __name__ == "__main__":
    main()
