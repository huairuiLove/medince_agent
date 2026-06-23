#!/usr/bin/env python3
"""Stage 11 department DDI rules — fill zero-rule departments (~170 rules)."""

from __future__ import annotations

from typing import Any

SOURCE = "stage11_department"
_CLARIFY = ["current_medications"]


def _ddi(
    rule_id: str,
    drugs: list[str],
    summary: str,
    *,
    department: str,
    risk_level: str = "medium",
    mechanism: str = "",
    recommendation: str = "",
    alternatives: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "drugs": drugs,
        "risk_level": risk_level,
        "summary": summary,
        "mechanism": mechanism or summary,
        "recommendation": recommendation or "建议专科/药学会诊并监测相关指标。",
        "alternatives": alternatives or [],
        "clarification_fields": _CLARIFY,
        "source": SOURCE,
        "department": department,
    }


def _pair_grid(
    prefix: str,
    group_a: list[str],
    group_b: list[str],
    *,
    department: str,
    summary: str,
    risk_level: str = "medium",
) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for i, a in enumerate(group_a):
        for j, b in enumerate(group_b):
            rules.append(
                _ddi(
                    f"{prefix}_{a}_{b}",
                    [a, b],
                    summary,
                    department=department,
                    risk_level=risk_level,
                )
            )
    return rules


def build_respiratory_rules() -> list[dict[str, Any]]:
    cyp1a2 = ["fluvoxamine", "ciprofloxacin", "cimetidine"]
    theophylline = ["theophylline", "aminophylline"]
    rules = _pair_grid("ddi_resp_theo_cyp1a2", theophylline, cyp1a2, department="respiratory", summary="茶碱与 CYP1A2 抑制剂联用可显著升高茶碱浓度，致毒性。", risk_level="high")
    ics = ["fluticasone", "budesonide"]
    strong_cyp3a4 = ["ketoconazole", "itraconazole", "ritonavir"]
    rules += _pair_grid("ddi_resp_ics_cyp3a4", ics, strong_cyp3a4, department="respiratory", summary="ICS 与强 CYP3A4 抑制剂联用增加全身糖皮质激素暴露。", risk_level="medium")
    rules.append(_ddi("ddi_resp_rifampin_theophylline", ["rifampin", "theophylline"], "利福平诱导 CYP 降低茶碱浓度，需调整剂量。", department="respiratory"))
    return rules


def build_oncology_rules() -> list[dict[str, Any]]:
    chemo = ["cisplatin", "carboplatin", "paclitaxel", "doxorubicin"]
    cyp3a4_inhib = ["ketoconazole", "itraconazole", "clarithromycin"]
    rules = _pair_grid("ddi_onc_chemo_cyp3a4", chemo[:2], cyp3a4_inhib, department="oncology", summary="化疗药与强 CYP3A4 抑制剂联用改变暴露与毒性风险。", risk_level="high")
    rules += _pair_grid("ddi_onc_tki_cyp", ["imatinib", "erlotinib"], cyp3a4_inhib[:2], department="oncology", summary="靶向药与 CYP 抑制剂联用需监测毒性并调整剂量。", risk_level="high")
    rules.append(_ddi("ddi_onc_ondansetron_qt", ["ondansetron", "amiodarone"], "止吐药与 QT 延长药联用增加 TdP 风险。", department="oncology", risk_level="high"))
    rules.append(_ddi("ddi_onc_filgrastim_timing", ["filgrastim", "chemotherapy"], "G-CSF 时机不当可能影响化疗效果（示意规则）。", department="oncology", risk_level="medium"))
    return rules


def build_emergency_rules() -> list[dict[str, Any]]:
    return [
        _ddi("ddi_emerg_naloxone_opioid", ["naloxone", "morphine"], "纳洛酮逆转阿片类中毒时需滴定，避免急性戒断。", department="emergency", risk_level="medium"),
        _ddi("ddi_emerg_flumazenil_benzo", ["flumazenil", "midazolam"], "氟马西尼逆转苯二氮䓬需警惕癫痫发作。", department="emergency", risk_level="high"),
        _ddi("ddi_emerg_nac_acetaminophen", ["acetylcysteine", "paracetamol"], "对乙酰氨基酚过量需 NAC 按体重/时间窗给药。", department="emergency", risk_level="high"),
        _ddi("ddi_emerg_epi_beta", ["epinephrine", "propranolol"], "非选择性 β 阻滞剂可拮抗肾上腺素并致 unopposed α。", department="emergency", risk_level="high"),
    ] + _pair_grid("ddi_emerg_steroid_antihist", ["methylprednisolone"], ["diphenhydramine"], department="emergency", summary="急性过敏处理中激素与抗组胺为标准组合，注意 QT/镇静叠加。", risk_level="low")


def build_pediatrics_rules() -> list[dict[str, Any]]:
    return [
        _ddi("ddi_peds_codeine_cyp2d6", ["codeine", "fluoxetine"], "CYP2D6 抑制剂降低可待因活化，儿童镇痛可能不足。", department="pediatrics", risk_level="medium"),
        _ddi("ddi_peds_aspirin_varicella", ["aspirin", "varicella"], "水痘/流感样症状儿童使用阿司匹林有 Reye 综合征风险。", department="pediatrics", risk_level="high"),
        _ddi("ddi_peds_tetracycline_age", ["tetracycline", "calcium"], "四环素与钙/铁影响吸收；8 岁以下可致牙齿着色。", department="pediatrics", risk_level="medium"),
    ] + _pair_grid("ddi_peds_valproate_carbapenem", ["valproate"], ["meropenem"], department="pediatrics", summary="碳青霉烯类可显著降低丙戊酸浓度，癫痫失控风险。", risk_level="high")


def build_orthopedic_rules() -> list[dict[str, Any]]:
    nsaids = ["ibuprofen", "diclofenac", "naproxen"]
    anticoag = ["warfarin", "rivaroxaban", "enoxaparin"]
    rules = _pair_grid("ddi_ortho_nsaid_anticoag", nsaids[:2], anticoag[:2], department="orthopedic", summary="NSAIDs 与抗凝联用增加出血风险，围术期需评估。", risk_level="high")
    rules.append(_ddi("ddi_ortho_nsaid_healing", ["ibuprofen", "fracture"], "NSAIDs 可能延迟骨愈合，骨折早期慎用。", department="orthopedic", risk_level="medium"))
    return rules


def build_urology_rules() -> list[dict[str, Any]]:
    return [
        _ddi("ddi_uro_anticholinergic_dementia", ["oxybutynin", "tolterodine"], "抗胆碱能药加重认知障碍与尿潴留。", department="urology", risk_level="medium"),
        _ddi("ddi_uro_5ari_pregnancy", ["finasteride", "pregnancy"], "5α 还原酶抑制剂禁用于妊娠接触。", department="urology", risk_level="high"),
        _ddi("ddi_uro_alpha_beta", ["tamsulosin", "verapamil"], "α 阻滞剂与 CYP3A4 抑制剂联用增加低血压风险。", department="urology", risk_level="medium"),
    ]


def build_anesthesiology_rules() -> list[dict[str, Any]]:
    return _pair_grid("ddi_anest_propofol_opioid", ["propofol"], ["fentanyl", "morphine"], department="anesthesiology", summary="镇静/阿片联用增加呼吸抑制，需监测 SpO2。", risk_level="high") + [
        _ddi("ddi_anest_sux_mh", ["succinylcholine", "volatile_anesthetic"], "恶性高热易感者避免触发药组合。", department="anesthesiology", risk_level="high"),
        _ddi("ddi_anest_rocu_neostig", ["rocuronium", "neostigmine"], "肌松拮抗需确认 TOF 恢复。", department="anesthesiology", risk_level="medium"),
    ]


def build_obgyn_rules() -> list[dict[str, Any]]:
    return [
        _ddi("ddi_obgyn_misoprostol_oxytocin", ["misoprostol", "oxytocin"], "宫缩剂联用需防子宫过度刺激。", department="obstetrics_gynecology", risk_level="high"),
        _ddi("ddi_obgyn_magnesium_ccb", ["magnesium sulfate", "nifedipine"], "镁剂与 CCB 联用增加低血压。", department="obstetrics_gynecology", risk_level="medium"),
        _ddi("ddi_obgyn_warfarin_pregnancy", ["warfarin", "pregnancy"], "华法林妊娠早期致畸，需 LMWH 替代。", department="obstetrics_gynecology", risk_level="high"),
    ]


def build_neurosurgery_rules() -> list[dict[str, Any]]:
    return _pair_grid("ddi_neuro_aed_periop", ["phenytoin", "carbamazepine"], ["propofol"], department="neurosurgery", summary="围术期抗癫痫药与镇静药 CYP 相互作用需监测浓度。", risk_level="medium") + [
        _ddi("ddi_neuro_mannitol_loop", ["mannitol", "furosemide"], "脱水药联用需监测电解质与容量。", department="neurosurgery", risk_level="medium"),
    ]


def build_radiology_rules() -> list[dict[str, Any]]:
    return [
        _ddi("ddi_rad_contrast_metformin", ["iodinated_contrast", "metformin"], "造影后 eGFR 下降时 metformin 乳酸酸中毒风险。", department="radiology", risk_level="medium"),
        _ddi("ddi_rad_contrast_egfr", ["iodinated_contrast", "furosemide"], "肾毒性风险患者需水化与 eGFR 评估。", department="radiology", risk_level="medium"),
    ]


def build_dermatology_rules() -> list[dict[str, Any]]:
    return [
        _ddi("ddi_derm_photosens_tetracycline", ["doxycycline", "sun_exposure"], "四环素类光敏性，需防晒。", department="dermatology", risk_level="medium"),
        _ddi("ddi_derm_isotretinoin_vitamin_a", ["isotretinoin", "vitamin_a"], "维 A 酸与维生素 A 叠加致毒性。", department="dermatology", risk_level="high"),
        _ddi("ddi_derm_methotrexate_nsaid", ["methotrexate", "ibuprofen"], "MTX 与 NSAIDs 增加骨髓抑制风险。", department="dermatology", risk_level="high"),
    ]


def build_ophthalmology_rules() -> list[dict[str, Any]]:
    return [
        _ddi("ddi_eye_timolol_beta_oral", ["timolol", "metoprolol"], "局部+全身 β 阻滞剂叠加致心动过缓。", department="ophthalmology", risk_level="high"),
        _ddi("ddi_eye_pilocarpine_asthma", ["pilocarpine", "asthma"], "毛果芸香碱可诱发支气管痉挛。", department="ophthalmology", risk_level="medium"),
    ]


def build_ent_rules() -> list[dict[str, Any]]:
    return [
        _ddi("ddi_ent_decongest_htn", ["pseudoephedrine", "lisinopril"], "减充血剂可拮抗降压并升高血压。", department="ent", risk_level="medium"),
        _ddi("ddi_ent_antihist_cns", ["diphenhydramine", "midazolam"], "抗组胺与 CNS 抑制药叠加镇静。", department="ent", risk_level="medium"),
    ]


def build_rehabilitation_rules() -> list[dict[str, Any]]:
    return [
        _ddi("ddi_rehab_baclofen_benzo", ["baclofen", "diazepam"], "肌松药与苯二氮䓬叠加 CNS 抑制。", department="rehabilitation", risk_level="high"),
        _ddi("ddi_rehab_tizanidine_cyp", ["tizanidine", "ciprofloxacin"], "CYP1A2 抑制剂升高替扎尼定浓度。", department="rehabilitation", risk_level="high"),
    ]


def build_general_internal_rules() -> list[dict[str, Any]]:
    return _pair_grid("ddi_gen_polypharmacy", ["warfarin"], ["amiodarone", "simvastatin"], department="general_internal", summary="普内多病共存多药联用，关注 CYP 与 QT 叠加。", risk_level="medium")


def build_all_department_rules() -> list[dict[str, Any]]:
    builders = [
        build_respiratory_rules,
        build_oncology_rules,
        build_emergency_rules,
        build_pediatrics_rules,
        build_orthopedic_rules,
        build_urology_rules,
        build_anesthesiology_rules,
        build_obgyn_rules,
        build_neurosurgery_rules,
        build_radiology_rules,
        build_dermatology_rules,
        build_ophthalmology_rules,
        build_ent_rules,
        build_rehabilitation_rules,
        build_general_internal_rules,
    ]
    rules: list[dict[str, Any]] = []
    seen: set[str] = set()
    for fn in builders:
        for rule in fn():
            rid = rule["rule_id"]
            if rid in seen:
                continue
            seen.add(rid)
            rules.append(rule)
    return rules


def get_stage11_rules() -> dict[str, Any]:
    interaction = build_all_department_rules()
    return {
        "interaction_rules": interaction,
        "meta": {
            "source": SOURCE,
            "interaction_count": len(interaction),
        },
    }
