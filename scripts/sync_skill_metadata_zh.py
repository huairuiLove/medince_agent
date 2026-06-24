#!/usr/bin/env python3
"""Sync Chinese skill titles/descriptions into datasets/agents/registry.yaml."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import datasets_path

REGISTRY_PATH = datasets_path("agents/registry.yaml")
AGENTS_ROOT = datasets_path("agents")

# skill_id -> (title, description) defaults; agent-specific overrides below
SKILL_TITLES: dict[str, tuple[str, str]] = {
    "base": ("专科基础能力", "专科医生身份、职责边界与会诊输出规范"),
    "heart_failure": ("心衰多药联合", "ACEI/ARB/ARNI、螺内酯、SGLT2i 与地高辛浓度监测"),
    "acs_protocol": ("ACS 抗栓方案", "DAPT 时长、P2Y12 与 PPI 联用、他汀与 CYP3A4 抑制剂"),
    "anticoag_bridge": ("抗凝桥接", "围术期华法林/DOAC 桥接与出血-血栓平衡"),
    "epilepsy_combo": ("抗癫痫联合用药", "多药联合、血药浓度与 CYP 诱导/抑制"),
    "parkinson_ddi": ("帕金森药物交互", "左旋多巴、MAO-B 抑制剂与抗精神病药交互"),
    "stroke_prevention": ("卒中二级预防", "抗血小板/抗凝、他汀与血压目标管理"),
    "chemo_ddi": ("化疗药物交互", "细胞毒药物与 CYP/QT/骨髓抑制叠加"),
    "immunosuppress": ("免疫抑制管理", "化疗/生物制剂与感染、TB 筛查及疫苗"),
    "antiemetic_combo": ("止吐方案联合", "5-HT3、NK1 与 QT/镇静叠加"),
    "pediatric_dosing": ("儿科剂量换算", "按体重/体表面积换算与年龄禁忌"),
    "growth_impact": ("生长发育影响", "激素、抗癫痫药对生长与发育的影响"),
    "vaccine_interaction": ("疫苗接种交互", "活疫苗与免疫抑制、接种时机"),
    "teratogen": ("致畸风险审查", "FDA 分级、致畸药物与避孕要求"),
    "lactation_safety": ("哺乳期用药安全", "乳汁排泄、婴儿暴露与替代方案"),
    "tocolysis": ("宫缩抑制剂审查", "β 激动剂、镁剂与母胎安全"),
    "vasoactive": ("血管活性药物", "升压/正性肌力药联用与心律失常风险"),
    "sedation_protocol": ("镇静镇痛方案", "阿片+苯二氮䓬呼吸抑制与撤药"),
    "crrt_adjustment": ("CRRT 剂量调整", "CRRT 日给药时机与肾排泄药物"),
    "copd_management": ("COPD 综合管理", "ICS/LABA/LAMA 联合与急性加重抗感染"),
    "inhaled_therapy": ("吸入治疗审查", "吸入激素与 CYP3A4 抑制剂全身暴露"),
    "respiratory_antibiotic": ("呼吸抗感染", "社区/院内肺炎抗菌谱与 QT/过敏"),
    "perioperative_anticoag": ("围术期抗凝", "术前停药、桥接与术后 VTE 预防"),
    "intracranial_htn": ("颅内压管理用药", "地塞米松、甘露醇与电解质监测"),
    "seizure_prophylaxis": ("癫痫预防用药", "围术期抗癫痫药选择与浓度监测"),
    "contrast_safety": ("造影剂安全", "碘/钆造影剂过敏、肾功能与 eGFR 阈值"),
    "metformin_hold": ("二甲双胍暂停", "增强 CT 前后暂停/恢复与乳酸酸中毒"),
    "allergy_premedication": ("造影剂过敏预处理", "预处理方案与 β 阻滞剂/哮喘交互"),
    "ppi_antiplatelet": ("PPI 与抗血小板", "PPI 与氯吡格雷 CYP2C19 及 GI 保护"),
    "ibd_immunosuppress": ("IBD 免疫抑制", "生物制剂/硫嘌呤与感染、TB 筛查"),
    "hepatic_metabolism": ("肝代谢与剂量", "Child-Pugh 分级下剂量与肝毒性上限"),
    "acute_toxicology": ("急性中毒处理", "NAC、阿片/苯二氮䓬拮抗与再中毒"),
    "resuscitation_drugs": ("复苏用药", "肾上腺素、钙剂与 β 阻滞剂/洋地黄交互"),
    "analgesia_sedation": ("急诊镇痛镇静", "阿片+苯二氮䓬呼吸抑制与休克下选择"),
    "high_alert_review": ("高警示药品", "抗凝、胰岛素、化疗、阿片双重核对"),
    "formulary_alignment": ("院目录一致性", "院内外购药偏差、替代与库存"),
    "pharmacy_ddi": ("药学 DDI 复核", "跨科室复杂 DDI 与剂量/途径合理性"),
    "polypharmacy": ("多重用药审查", "≥5 种药物时重复成分与抗胆碱负荷"),
    "chronic_disease_combo": ("慢病联合用药", "三高联合与 eGFR 相关调整"),
    "comorbidity_risk": ("合并症风险", "CKD、肝病、心衰时的剂量与禁忌"),
    "renal_dose_adjust": ("肾剂量调整", "按 eGFR 调整 DOAC、氨基糖苷等"),
    "hyperkalemia_risk": ("高钾风险", "ACEI/ARB+螺内酯+保钾利尿剂叠加"),
    "dialysis_medication": ("透析用药", "透析日给药时机与造影剂肾病预防"),
    "diabetes_combo": ("糖尿病多药联合", "磺脲重复、胰岛素+SGLT2 低血糖/脱水"),
    "thyroid_ddi": ("甲状腺用药", "左甲状腺素吸收间隔与胺碘酮致甲功异常"),
    "steroid_management": ("激素管理", "应激剂量、库欣与降糖方案调整"),
    "beers_criteria": ("Beers 准则", "苯二氮䓬、抗胆碱能药等老年禁忌"),
    "fall_risk": ("跌倒风险", "镇静/降压/α 阻滞剂致体位性低血压"),
    "deprescribing": ("去处方化", "冗余 PPI、苯二氮䓬与重复成分精简"),
    "mtx_monitoring": ("MTX 监测", "MTX+NSAIDs/甲氧苄啶毒性；叶酸与 LFT"),
    "biologic_infection": ("生物制剂感染", "TNF 抑制剂与活动性感染/TB；活疫苗"),
    "nsaid_gi_risk": ("NSAIDs 胃肠道风险", "NSAIDs+抗凝/激素 GI 出血与肾毒性"),
    "antibiotic_spectrum": ("抗感染谱系", "经验/目标治疗谱系与交叉过敏"),
    "resistance_stewardship": ("耐药管理", "碳青霉烯/万古霉素/利奈唑胺指征与 TDM"),
    "hiv_tb_antifungal": ("HIV/TB/真菌 DDI", "抗结核/HIV/抗真菌与 CYP 强抑制/诱导"),
    "nsaid_bone_healing": ("NSAIDs 与骨愈合", "NSAIDs 对骨愈合影响及出血风险"),
    "vte_prophylaxis": ("VTE 预防", "LMWH/DOAC 剂量、肾功能与硬膜外禁忌"),
    "alpha_blocker_hypotension": ("α 阻滞剂低血压", "多种 α 阻滞剂与 PDE5 抑制剂"),
    "anticoag_prostate": ("前列腺围术期抗凝", "前列腺手术/活检围术期抗凝管理"),
    "renal_stone_analgesia": ("泌尿系绞痛镇痛", "结石 NSAIDs/阿片与肾毒性药物"),
    "induction_agents": ("麻醉诱导用药", "诱导药+阿片/苯二氮䓬呼吸抑制与 QT"),
    "anticoag_periop": ("麻醉围术期抗凝", "区域麻醉与抗凝/抗血小板时间窗"),
    "malignant_hyperthermia": ("恶性高热", "挥发性麻醉/琥珀胆碱与丹曲林准备"),
    "serotonergic_syndrome": ("五羟色胺综合征", "SSRI+曲马多/MAOI/利奈唑胺等"),
    "qt_psychotropics": ("精神药物 QT 延长", "抗精神病+大环内酯/氟喹诺酮 QT 风险"),
    "mood_stabilizer": ("心境稳定剂", "锂盐+NSAIDs/ACEI 致锂中毒；丙戊酸交互"),
    "systemic_immunosuppress": ("系统免疫抑制", "MTX/环孢素与感染、肝毒性"),
    "retinoid_teratogenicity": ("维 A 酸致畸", "异维 A 酸/阿维 A 酯致畸与避孕"),
    "topical_systemic": ("外用与全身叠加", "外用激素/β 阻滞剂与系统用药叠加"),
    "ocular_toxicity": ("眼毒性审查", "胺碘酮/羟氯喹等药物性视网膜/角膜病变"),
    "topical_beta_blocker": ("局部 β 阻滞剂", "噻吗洛尔滴眼液+口服 β 阻滞剂"),
    "glaucoma_systemic": ("青光眼系统用药", "碳酸酐酶抑制剂与磺胺过敏"),
    "ototoxicity": ("耳毒性", "氨基糖苷/袢利尿剂耳毒性与听力监测"),
    "airway_sedation": ("气道与镇静", "上气道手术镇静与误吸风险"),
    "postop_analgesia": ("头颈术后镇痛", "NSAIDs/阿片与抗凝出血平衡"),
    "stroke_secondary_prevention": ("卒中二级预防", "抗血小板/抗凝、他汀与出血风险"),
    "spasticity_mgmt": ("痉挛管理", "巴氯芬/替扎尼定与镇静、肝毒性"),
    "long_term_polypharmacy": ("长期多重用药", "康复期去处方化与功能优化"),
    # core agent skills
    "ddi_review": ("药物相互作用", "CYP、QT、药效学相互作用审查"),
    "dose_review": ("剂量与给药", "剂量、途径、频次与肾功能调整"),
    "duplicate_review": ("重复用药", "重复成分与同类药叠加"),
    "indication_match": ("适应证匹配", "候选药与诊断/适应证一致性"),
    "comorbidity": ("合并症评估", "多病共存下的用药路径与 off-label"),
    "cross_allergy": ("交叉过敏", "同类/交叉结构过敏与替代"),
    "adr_history": ("既往 ADR", "既往不良反应与再暴露风险"),
    "formulary_check": ("院目录审查", "候选药是否在院 formulary"),
    "stock_alternative": ("缺货替代", "缺货/非目录时的院内可调配替代"),
    "pregnancy": ("妊娠用药", "FDA 分级、致畸风险与替代方案"),
    "anticoagulation": ("抗凝管理", "华法林/DOAC 桥接、出血与监测"),
    "geriatric": ("老年用药", "Beers 准则、跌倒与肾功能调整"),
}

AGENT_SKILL_OVERRIDES: dict[str, dict[str, tuple[str, str]]] = {
    "neurosurgery_specialist": {
        "perioperative_anticoag": ("颅脑围术期抗凝", "颅脑手术抗凝桥接与再出血风险"),
    },
    "orthopedic_specialist": {
        "perioperative_anticoag": ("骨科围术期抗凝", "关节/脊柱手术抗凝桥接与出血平衡"),
    },
}


def skill_meta(agent_id: str, skill_id: str, md_path: Path) -> dict[str, str]:
    overrides = AGENT_SKILL_OVERRIDES.get(agent_id, {})
    if skill_id in overrides:
        title, desc = overrides[skill_id]
    elif skill_id in SKILL_TITLES:
        title, desc = SKILL_TITLES[skill_id]
    else:
        title = skill_id.replace("_", " ")
        desc = ""
    if md_path.exists():
        first_line = md_path.read_text(encoding="utf-8").strip().splitlines()[0].strip()
        if first_line and not desc:
            desc = first_line[:120]
    return {"id": skill_id, "title": title, "description": desc, "file": f"{skill_id}.md"}


def structured_skills(agent_id: str, skill_ids: list[str]) -> list[dict[str, str]]:
    agent_dir = AGENTS_ROOT / agent_id
    return [skill_meta(agent_id, sid, agent_dir / f"{sid}.md") for sid in skill_ids]


def main() -> None:
    with REGISTRY_PATH.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    # Core agents: add descriptions, rename specialist, fix formulary label
    specialist = raw["agents"]["specialist"]
    specialist["agent_name"] = "特殊人群审查专员"
    specialist["role"] = "妊娠/哺乳、抗凝、老年等特殊人群专科禁忌审查"
    for skill in specialist.get("skills", []):
        if isinstance(skill, dict) and skill["id"] in SKILL_TITLES:
            skill["title"], skill["description"] = SKILL_TITLES[skill["id"]]

    pharmacy = raw["agents"]["pharmacy_inventory"]
    for skill in pharmacy.get("skills", []):
        if isinstance(skill, dict) and skill["id"] == "formulary_check":
            skill["title"] = "院目录审查"
            skill["description"] = "候选药是否在院 formulary、目录偏差"

    for agent_key in ("clinical_pharmacist", "internal_medicine", "allergy_specialist"):
        for skill in raw["agents"][agent_key].get("skills", []):
            if isinstance(skill, dict) and skill["id"] in SKILL_TITLES:
                t, d = SKILL_TITLES[skill["id"]]
                skill.setdefault("description", d)
                if skill.get("title") == skill["id"]:
                    skill["title"] = t

    dept_agents = raw.get("department_agents") or {}
    for agent_id, entry in dept_agents.items():
        raw_skills = entry.get("skills") or []
        if raw_skills and isinstance(raw_skills[0], str):
            skill_ids = list(raw_skills)
        else:
            skill_ids = [s["id"] for s in raw_skills if isinstance(s, dict)]
        entry["skills"] = structured_skills(agent_id, skill_ids)
        entry["default_skills"] = skill_ids

    with REGISTRY_PATH.open("w", encoding="utf-8") as fh:
        yaml.dump(raw, fh, allow_unicode=True, sort_keys=False, default_flow_style=False)

    print(f"Updated {len(dept_agents)} department agents with Chinese skill metadata")


if __name__ == "__main__":
    main()
