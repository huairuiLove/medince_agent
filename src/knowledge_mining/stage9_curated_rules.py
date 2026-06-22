"""Stage 9 curated clinical safety rules — population, allergy, department DDI."""

from __future__ import annotations

from typing import Any

SOURCE = "stage9_curated"
_CLARIFY_MEDS = ["current_medications"]
_CLARIFY_POP = ["pregnancy_status", "age", "egfr"]
_CLARIFY_ALLERGY = ["allergies"]


def _interaction(
    rule_id: str,
    drugs: list[str],
    risk_level: str,
    summary: str,
    mechanism: str,
    recommendation: str,
    alternatives: list[str] | None = None,
    department: str | None = None,
    clarification_fields: list[str] | None = None,
) -> dict[str, Any]:
    rule: dict[str, Any] = {
        "rule_id": rule_id,
        "drugs": drugs,
        "risk_level": risk_level,
        "summary": summary,
        "mechanism": mechanism,
        "recommendation": recommendation,
        "alternatives": alternatives or [],
        "clarification_fields": clarification_fields or _CLARIFY_MEDS,
        "source": SOURCE,
    }
    if department:
        rule["department"] = department
    return rule


def _pairwise_interactions(
    group_a: list[str],
    group_b: list[str],
    *,
    rule_id_prefix: str,
    risk_level: str,
    summary: str,
    mechanism: str,
    recommendation: str,
    alternatives: list[str] | None = None,
    department: str | None = None,
    skip_same: bool = True,
) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for drug_a in group_a:
        for drug_b in group_b:
            if skip_same and drug_a == drug_b:
                continue
            pair = sorted([drug_a, drug_b])
            rule_id = f"{rule_id_prefix}_{pair[0]}_{pair[1]}"
            rules.append(
                _interaction(
                    rule_id=rule_id,
                    drugs=pair,
                    risk_level=risk_level,
                    summary=summary,
                    mechanism=mechanism,
                    recommendation=recommendation,
                    alternatives=alternatives,
                    department=department,
                )
            )
    return rules


def _within_group_pairwise(
    drugs: list[str],
    *,
    rule_id_prefix: str,
    risk_level: str,
    summary: str,
    mechanism: str,
    recommendation: str,
    department: str | None = None,
) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for i, drug_a in enumerate(drugs):
        for drug_b in drugs[i + 1 :]:
            pair = sorted([drug_a, drug_b])
            rules.append(
                _interaction(
                    rule_id=f"{rule_id_prefix}_{pair[0]}_{pair[1]}",
                    drugs=pair,
                    risk_level=risk_level,
                    summary=summary,
                    mechanism=mechanism,
                    recommendation=recommendation,
                    department=department,
                )
            )
    return rules


def _population(
    rule_id: str,
    trigger_drugs: list[str],
    population_field: str,
    risk_level: str,
    summary: str,
    mechanism: str,
    recommendation: str,
    alternatives: list[str] | None = None,
    clarification_fields: list[str] | None = None,
    **field_constraints: Any,
) -> dict[str, Any]:
    rule: dict[str, Any] = {
        "rule_id": rule_id,
        "trigger_drugs": trigger_drugs,
        "population_field": population_field,
        "risk_level": risk_level,
        "summary": summary,
        "mechanism": mechanism,
        "recommendation": recommendation,
        "alternatives": alternatives or [],
        "clarification_fields": clarification_fields or _CLARIFY_POP,
        "source": SOURCE,
    }
    rule.update(field_constraints)
    return rule


def _pregnancy_rules_for_drugs(
    drugs: list[str],
    *,
    mechanism: str,
    summary_template: str,
    recommendation: str,
    risk_level: str = "high",
) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for drug in drugs:
        rules.append(
            _population(
                rule_id=f"pop_pregnancy_{drug}",
                trigger_drugs=[drug],
                population_field="pregnancy_status",
                match_values=["pregnant"],
                risk_level=risk_level,
                summary=summary_template.format(drug=drug),
                mechanism=mechanism,
                recommendation=recommendation,
                clarification_fields=["pregnancy_status"],
            )
        )
    return rules


def _scenario(
    rule_id: str,
    scenario_type: str,
    risk_level: str,
    summary: str,
    mechanism: str,
    recommendation: str,
    *,
    department: str | None = None,
    clarification_fields: list[str] | None = None,
    **constraints: Any,
) -> dict[str, Any]:
    rule: dict[str, Any] = {
        "rule_id": rule_id,
        "scenario_type": scenario_type,
        "risk_level": risk_level,
        "summary": summary,
        "mechanism": mechanism,
        "recommendation": recommendation,
        "alternatives": [],
        "clarification_fields": clarification_fields or _CLARIFY_MEDS,
        "source": SOURCE,
    }
    if department:
        rule["department"] = department
    rule.update(constraints)
    return rule


def build_scenario_rules() -> list[dict[str, Any]]:
    return [
        _scenario(
            "scenario_polypharmacy_5plus",
            "polypharmacy",
            "medium",
            "患者同时用药 ≥5 种，需系统性 DDI 与重复用药筛查。",
            "多药联用增加相互作用与依从性风险。",
            "建议逐条核对适应症、重复成分与高危组合。",
            department="geriatrics",
            min_total_drugs=5,
        ),
        _scenario(
            "scenario_fall_risk_combo",
            "fall_risk_combo",
            "high",
            "检测到跌倒四联组分（苯二氮卓+阿片类+降压药+利尿剂）叠加，老年跌倒风险极高。",
            "镇静、直立性低血压与电解质紊乱叠加。",
            "优先减停非必需药物，加强跌倒防护与监护。",
            department="geriatrics",
            drug_classes={
                "benzodiazepine": BENZODIAZEPINES,
                "opioid": OPIOIDS,
                "antihypertensive": ANTIHYPERTENSIVES_FALL,
                "diuretic": DIURETICS,
            },
        ),
        _scenario(
            "scenario_renal_age_adjustment",
            "renal_age_adjustment",
            "medium",
            "年龄 ≥75 岁且 eGFR <45，经肾排泄药物需评估剂量。",
            "老年肾功能减退导致药物蓄积风险。",
            "核对肾剂量调整指南，监测肾功能与药物浓度。",
            department="geriatrics",
            age_min=75,
            egfr_max=45,
        ),
        _scenario(
            "scenario_anticholinergic_burden_3plus",
            "anticholinergic_burden",
            "high",
            "抗胆碱能负荷 ≥3（多种抗胆碱能药叠加），老年认知/尿潴留风险升高。",
            "抗胆碱能效应累积。",
            "评估减药或换用低负担替代方案。",
            department="geriatrics",
            min_drug_count=3,
            drug_list=ANTICHOLINERGICS,
        ),
    ]


def _allergy(
    rule_id: str,
    allergy_terms: list[str],
    trigger_drugs: list[str],
    risk_level: str,
    summary: str,
    mechanism: str,
    recommendation: str,
    alternatives: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "allergy_terms": allergy_terms,
        "trigger_drugs": trigger_drugs,
        "risk_level": risk_level,
        "summary": summary,
        "mechanism": mechanism,
        "recommendation": recommendation,
        "alternatives": alternatives or [],
        "clarification_fields": _CLARIFY_ALLERGY,
        "source": SOURCE,
    }


# ── Drug class constants ───────────────────────────────────────────────────

ACE_INHIBITORS = [
    "lisinopril",
    "captopril",
    "enalapril",
    "perindopril",
    "ramipril",
    "benazepril",
    "fosinopril",
    "quinapril",
]
ARBS = [
    "losartan",
    "valsartan",
    "irbesartan",
    "candesartan",
    "telmisartan",
    "olmesartan",
]
STATINS = [
    "atorvastatin",
    "simvastatin",
    "rosuvastatin",
    "pravastatin",
    "fluvastatin",
]
FLUOROQUINOLONES = ["levofloxacin", "moxifloxacin", "ciprofloxacin"]
TETRACYCLINES = ["doxycycline", "tetracycline", "minocycline"]
PREGNANCY_OTHER = [
    "warfarin",
    "methotrexate",
    "isotretinoin",
    "valproic acid",
    "lithium",
    "finasteride",
    "ribavirin",
    "leflunomide",
    "mycophenolate",
    "spironolactone",
    "carbimazole",
    "misoprostol",
    "ergotamine",
]
BENZODIAZEPINES = ["diazepam", "alprazolam", "clonazepam", "lorazepam", "temazepam", "flurazepam"]
BETA_BLOCKERS = ["metoprolol", "atenolol", "propranolol", "bisoprolol", "carvedilol"]
CCB_NON_DHP = ["verapamil", "diltiazem"]
DOACS = ["rivaroxaban", "apixaban", "dabigatran"]
NSAIDS = ["ibuprofen", "diclofenac", "naproxen", "indomethacin", "aspirin"]
SSRIS = ["fluoxetine", "sertraline", "paroxetine", "escitalopram", "citalopram"]
OPIOIDS = ["morphine", "fentanyl", "oxycodone", "hydrocodone", "tramadol"]
SULFONYLUREAS = ["glibenclamide", "glimepiride", "gliclazide"]
SGLT2_INHIBITORS = ["empagliflozin", "dapagliflozin", "canagliflozin"]
CYP3A4_INHIBITORS = [
    "clarithromycin",
    "itraconazole",
    "ketoconazole",
    "voriconazole",
    "fluconazole",
    "amiodarone",
    "cyclosporine",
]
QT_PROLONGING = [
    "sotalol",
    "amiodarone",
    "moxifloxacin",
    "haloperidol",
    "ondansetron",
    "azithromycin",
    "citalopram",
]
MAO_INHIBITORS = ["phenelzine", "tranylcypromine", "isocarboxazid", "selegiline"]
TRIPTANS = ["sumatriptan", "rizatriptan", "zolmitriptan"]
ANTIEPILEPTIC_INDUCERS = ["phenobarbital", "carbamazepine", "phenytoin"]
AMINOGLYCOSIDES = ["gentamicin", "tobramycin", "amikacin"]
POTASSIUM_SUPPLEMENTS = ["potassium chloride", "potassium citrate"]
PPI_STRONG = ["omeprazole", "esomeprazole"]
PPI_WEAK = ["lansoprazole", "pantoprazole"]
PDE5_INHIBITORS = ["sildenafil", "tadalafil"]
NITRATES = ["nitroglycerin", "isosorbide dinitrate", "isosorbide mononitrate"]
ANTIPSYCHOTICS = ["haloperidol", "quetiapine", "olanzapine", "risperidone", "clozapine"]
TCAS = ["amitriptyline", "nortriptyline", "imipramine"]
ANTICHOLINERGICS = [
    "oxybutynin",
    "diphenhydramine",
    "chlorpheniramine",
    "promethazine",
    "amitriptyline",
    "metoclopramide",
]
DIURETICS = ["furosemide", "hydrochlorothiazide", "spironolactone", "torsemide"]
ANTIHYPERTENSIVES_FALL = ["amlodipine", "losartan", "metoprolol", "doxazosin", "clonidine"]


def build_population_rules() -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []

    pregnancy_drugs = ACE_INHIBITORS + ARBS + STATINS + FLUOROQUINOLONES + TETRACYCLINES + PREGNANCY_OTHER
    rules.extend(
        _pregnancy_rules_for_drugs(
            pregnancy_drugs,
            mechanism="妊娠期暴露可致胎儿发育异常或致畸。",
            summary_template="{drug} 在妊娠期使用存在胎儿安全风险。",
            recommendation="妊娠期避免使用，需由专科评估替代方案。",
            risk_level="high",
        )
    )
    for drug in TETRACYCLINES:
        for rule in rules:
            if rule["rule_id"] == f"pop_pregnancy_{drug}":
                rule["risk_level"] = "medium"
                rule["mechanism"] = "四环素类可致胎儿牙齿着色及骨生长抑制。"

    lactation_drugs = [
        ("methotrexate", "high", "甲氨蝶呤可分泌入乳汁，致婴儿免疫抑制。"),
        ("lithium", "high", "锂盐乳汁浓度高，可致婴儿中毒。"),
        ("amiodarone", "high", "胺碘酮含高碘，可致婴儿甲状腺功能异常。"),
        ("chloramphenicol", "high", "氯霉素可致婴儿灰婴综合征。"),
        ("isotretinoin", "high", "异维A酸可分泌入乳汁。"),
        ("ergotamine", "high", "麦角胺可抑制泌乳并致婴儿中毒。"),
        ("cyclophosphamide", "high", "环磷酰胺可分泌入乳汁，存在免疫抑制风险。"),
        ("gold sodium thiomalate", "medium", "金制剂可分泌入乳汁。"),
    ]
    for drug, risk, summary in lactation_drugs:
        rules.append(
            _population(
                rule_id=f"pop_lactation_{drug.replace(' ', '_')}",
                trigger_drugs=[drug],
                population_field="lactation",
                match_values=["lactating", "breastfeeding", "哺乳"],
                risk_level=risk,
                summary=summary,
                mechanism="药物可进入乳汁并对乳儿产生毒性或抑制泌乳。",
                recommendation="哺乳期避免使用，必要时暂停哺乳或更换方案。",
                clarification_fields=["lactation"],
            )
        )

    pediatric_rules = [
        ("aspirin", 16, None, "high", "儿童使用阿司匹林存在 Reye 综合征风险。"),
        ("doxycycline", None, 8, "high", "8 岁以下儿童使用四环素类可致牙齿永久着色。"),
        ("tetracycline", None, 8, "high", "8 岁以下儿童使用四环素类可致牙齿永久着色。"),
        ("minocycline", None, 8, "high", "8 岁以下儿童使用四环素类可致牙齿永久着色。"),
        ("levofloxacin", 18, None, "medium", "18 岁以下使用氟喹诺酮类存在关节软骨损伤风险。"),
        ("moxifloxacin", 18, None, "medium", "18 岁以下使用氟喹诺酮类存在关节软骨损伤风险。"),
        ("ciprofloxacin", 18, None, "medium", "18 岁以下使用氟喹诺酮类存在关节软骨损伤风险。"),
        ("chloramphenicol", 2, None, "high", "新生儿/小婴儿使用氯霉素可致灰婴综合征。"),
        ("codeine", 12, None, "high", "12 岁以下使用可待因存在呼吸抑制风险。"),
        ("tramadol", 12, None, "high", "12 岁以下使用曲马多存在呼吸抑制风险。"),
        ("phenobarbital", 1, None, "medium", "新生儿使用苯巴比妥易致过度镇静。"),
        ("valproic acid", 2, None, "high", "2 岁以下使用丙戊酸肝毒性风险显著增加。"),
        ("chlorpheniramine", 2, None, "medium", "2 岁以下使用第一代抗组胺药可致过度镇静。"),
        ("dextromethorphan", 4, None, "medium", "4 岁以下使用右美沙芬存在呼吸抑制风险。"),
    ]
    for drug, age_min, age_max, risk, summary in pediatric_rules:
        constraints: dict[str, Any] = {}
        if age_min is not None:
            constraints["age_min"] = age_min
        if age_max is not None:
            constraints["age_max"] = age_max
        rules.append(
            _population(
                rule_id=f"pop_pediatric_{drug.replace(' ', '_')}",
                trigger_drugs=[drug],
                population_field="age",
                risk_level=risk,
                summary=summary,
                mechanism="儿童特殊人群药代动力学及不良反应谱与成人不同。",
                recommendation="除明确专科指征外，应避免或在严密监测下使用。",
                clarification_fields=["age"],
                **constraints,
            )
        )

    beers_drugs = [
        ("diazepam", "high", "长效苯二氮卓在老年患者中增加跌倒、骨折及认知损害风险。"),
        ("alprazolam", "medium", "苯二氮卓类在老年患者中增加跌倒风险。"),
        ("clonazepam", "medium", "苯二氮卓类在老年患者中增加跌倒风险。"),
        ("lorazepam", "medium", "苯二氮卓类在老年患者中增加跌倒风险。"),
        ("temazepam", "medium", "苯二氮卓类在老年患者中增加跌倒风险。"),
        ("flurazepam", "high", "长效苯二氮卓在老年患者中增加跌倒及认知损害风险。"),
        ("glibenclamide", "high", "长效磺脲类在老年患者中易致严重低血糖。"),
        ("digoxin", "medium", "地高辛治疗窗窄，老年患者中毒风险增加。"),
        ("amitriptyline", "high", "三环抗抑郁药在老年患者中抗胆碱能及直立低血压风险高。"),
        ("chlorpheniramine", "medium", "第一代抗组胺药在老年患者中抗胆碱能负担高。"),
        ("diphenhydramine", "medium", "苯海拉明在老年患者中抗胆碱能负担高。"),
        ("promethazine", "medium", "异丙嗪在老年患者中抗胆碱能及镇静风险高。"),
        ("oxybutynin", "medium", "奥昔布宁在老年患者中可致尿潴留、便秘及认知损害。"),
        ("dipyridamole", "medium", "双嘧达莫在老年患者中可致直立低血压。"),
        ("nitrofurantoin", "medium", "肾功能减退时呋喃妥因肺毒性风险增加。"),
        ("metoclopramide", "high", "甲氧氯普胺在老年患者中可致迟发性运动障碍。"),
        ("indomethacin", "high", "吲哚美辛在老年患者中 GI 出血及肾毒性风险最高。"),
        ("meperidine", "high", "哌替啶代谢物在老年患者中蓄积，可致癫痫及神经毒性。"),
        ("amiodarone", "medium", "胺碘酮在老年患者中甲状腺、肺及肝毒性风险增加。"),
        ("clonidine", "medium", "可乐定在老年患者中可致直立低血压及过度镇静。"),
        ("doxazosin", "medium", "多沙唑嗪在老年患者中可致直立低血压。"),
        ("naproxen", "medium", "萘普生在老年患者中 GI 出血风险增加。"),
        ("hydroxyzine", "medium", "羟嗪在老年患者中抗胆碱能负担高。"),
        ("paroxetine", "medium", "帕罗西汀在老年患者中抗胆碱能及跌倒风险增加。"),
        ("cyclobenzaprine", "medium", "环苯扎林在老年患者中抗胆碱能及镇静风险高。"),
    ]
    for drug, risk, summary in beers_drugs:
        rules.append(
            _population(
                rule_id=f"pop_beers_{drug.replace(' ', '_')}",
                trigger_drugs=[drug],
                population_field="age",
                age_min=65,
                age_compare="gte",
                risk_level=risk,
                summary=summary,
                mechanism="Beers 准则：该药在≥65 岁患者中风险获益比不佳。",
                recommendation="老年患者优先评估非 Beers 名单替代方案。",
                clarification_fields=["age"],
            )
        )

    renal_rules = [
        ("metformin", 30, "high", "eGFR<30 时二甲双胍禁用，乳酸酸中毒风险增加。"),
        ("dabigatran", 30, "high", "eGFR<30 时达比加群禁用，出血风险显著增加。"),
        ("rivaroxaban", 15, "high", "eGFR<15 时利伐沙班禁用。"),
        ("enoxaparin", 30, "medium", "eGFR<30 时需减量或换用普通肝素。"),
        ("vancomycin", 50, "medium", "eGFR<50 时万古霉素需 TDM 调量。"),
        ("gentamicin", 60, "high", "eGFR<60 时氨基糖苷类需 TDM 并监测耳肾毒性。"),
        ("gabapentin", 30, "medium", "eGFR<30 时加巴喷丁需大幅减量。"),
        ("pregabalin", 30, "medium", "eGFR<30 时普瑞巴林需大幅减量。"),
        ("methotrexate", 30, "high", "eGFR<30 时甲氨蝶呤禁用，骨髓抑制风险增加。"),
        ("spironolactone", 30, "high", "eGFR<30 时螺内酯禁用，高钾血症风险增加。"),
    ]
    for drug, egfr_max, risk, summary in renal_rules:
        rules.append(
            _population(
                rule_id=f"pop_renal_{drug.replace(' ', '_')}",
                trigger_drugs=[drug],
                population_field="egfr",
                egfr_max=egfr_max,
                risk_level=risk,
                summary=summary,
                mechanism="肾功能减退时药物清除下降，毒性风险增加。",
                recommendation="根据 eGFR 调整剂量或禁用，并加强监测。",
                clarification_fields=["egfr"],
            )
        )

    hepatic_rules = [
        (STATINS, "high", "活动性肝病或转氨酶持续升高时使用他汀类风险增加。"),
        (["acetaminophen"], "medium", "严重肝病时对乙酰氨基酚日剂量应限制在 2g 以内。"),
        (BENZODIAZEPINES, "high", "严重肝病时使用苯二氮卓类可加重肝性脑病。"),
        (["warfarin"], "high", "严重肝病时华法林 INR 难以预测。"),
        (["methotrexate"], "high", "肝病时甲氨蝶呤肝毒性风险显著增加。"),
        (["amiodarone"], "medium", "肝病时胺碘酮肝毒性叠加风险增加。"),
        (["isoniazid"], "high", "肝病时异烟肼肝毒性风险显著增加。"),
        (["pyrazinamide"], "high", "肝病时吡嗪酰胺禁用。"),
    ]
    for drugs, risk, summary in hepatic_rules:
        drug_key = drugs[0] if len(drugs) == 1 else "statins"
        rules.append(
            _population(
                rule_id=f"pop_hepatic_{drug_key.replace(' ', '_')}",
                trigger_drugs=drugs if len(drugs) > 1 else drugs,
                population_field="hepatic",
                match_values=["severe", "active_liver_disease", "cirrhosis", "肝病", "liver_failure"],
                risk_level=risk,
                summary=summary,
                mechanism="肝功能不全时药物代谢受损，毒性风险增加。",
                recommendation="严重肝病时避免使用或严格限制剂量并监测肝功能。",
                clarification_fields=["hepatic"],
            )
        )

    return rules


def build_allergy_rules() -> list[dict[str, Any]]:
    return [
        _allergy(
            "alg_beta_lactam_penicillins",
            ["penicillin", "青霉素"],
            ["amoxicillin", "ampicillin", "piperacillin"],
            "high",
            "青霉素过敏患者使用阿莫西林/氨苄西林/哌拉西林存在交叉过敏风险。",
            "β-内酰胺类同族交叉过敏风险高。",
            "避免使用，确认过敏史并评估非青霉素方案。",
        ),
        _allergy(
            "alg_beta_lactam_to_cephalosporin",
            ["penicillin", "青霉素"],
            ["cephalexin", "cefuroxime", "ceftriaxone", "cefepime"],
            "medium",
            "青霉素过敏患者使用头孢类存在低概率交叉过敏（约1-3%）。",
            "β-内酰胺侧链相似性导致低度交叉反应。",
            "谨慎使用，必要时皮试或选用非 β-内酰胺替代。",
        ),
        _allergy(
            "alg_beta_lactam_to_carbapenem",
            ["penicillin", "青霉素"],
            ["meropenem", "imipenem", "ertapenem"],
            "low",
            "青霉素过敏患者使用碳青霉烯类交叉过敏概率极低（<1%）。",
            "碳青霉烯与青霉素交叉反应率低。",
            "可在严密监测下评估使用。",
        ),
        _allergy(
            "alg_cephalosporin_cross",
            ["cephalosporin", "头孢"],
            ["cephalexin", "cefuroxime", "ceftriaxone", "cefepime"],
            "medium",
            "头孢过敏患者使用其他头孢存在交叉过敏风险。",
            "头孢侧链相似性导致族内交叉反应。",
            "避免同族再暴露，评估不同代头孢或替代抗菌方案。",
        ),
        _allergy(
            "alg_nsaid_cross",
            ["aspirin", "阿司匹林", "nsaid", "布洛芬"],
            ["ibuprofen", "diclofenac", "naproxen", "indomethacin"],
            "high",
            "NSAIDs 过敏患者使用其他非选择性 NSAIDs 存在交叉过敏风险。",
            "COX-1 机制相关的类效应。",
            "避免 NSAIDs，优先对乙酰氨基酚或其他非 NSAID 方案。",
        ),
        _allergy(
            "alg_nsaid_to_cox2",
            ["aspirin", "nsaid"],
            ["celecoxib", "etoricoxib"],
            "low",
            "NSAIDs 过敏患者使用 COX-2 抑制剂交叉过敏概率较低。",
            "COX-2 选择性较高，交叉反应率低。",
            "可在评估后谨慎试用。",
        ),
        _allergy(
            "alg_sulfonamide_antibacterial",
            ["sulfonamide", "磺胺"],
            ["sulfamethoxazole", "sulfasalazine"],
            "medium",
            "磺胺过敏患者使用磺胺抗菌药存在过敏风险。",
            "磺胺母核交叉反应。",
            "避免磺胺类抗菌药，选用替代方案。",
        ),
        _allergy(
            "alg_sulfonamide_non_antibacterial",
            ["sulfonamide", "磺胺"],
            ["furosemide", "celecoxib", "glimepiride", "hydrochlorothiazide"],
            "low",
            "磺胺过敏患者使用非抗菌磺胺药交叉过敏证据有限。",
            "非抗菌磺胺与抗菌磺胺交叉反应争议较大。",
            "可在评估获益风险后谨慎使用。",
        ),
        _allergy(
            "alg_iodine_contrast",
            ["iodine", "碘", "contrast", "造影剂"],
            ["iohexol", "iopamidol", "iodixanol"],
            "high",
            "碘/造影剂过敏史患者再次使用碘造影剂存在过敏风险。",
            "碘造影剂过敏反应。",
            "需预处理、换用非离子造影剂或在严密监测下使用。",
        ),
        _allergy(
            "alg_ester_local_anesthetic",
            ["procaine", "普鲁卡因"],
            ["tetracaine", "benzocaine"],
            "medium",
            "酯类局麻药过敏患者使用其他酯类局麻药交叉过敏风险高。",
            "PABA 代谢产物交叉反应。",
            "改用酰胺类局麻药。",
        ),
        _allergy(
            "alg_amide_local_anesthetic",
            ["lidocaine", "利多卡因"],
            ["bupivacaine", "ropivacaine"],
            "low",
            "酰胺类局麻药之间交叉过敏概率较低。",
            "酰胺类交叉反应率低。",
            "可在监测下评估替代酰胺类。",
        ),
        _allergy(
            "alg_macrolide_cross",
            ["erythromycin", "红霉素"],
            ["azithromycin", "clarithromycin"],
            "medium",
            "大环内酯过敏患者使用其他大环内酯存在交叉过敏风险。",
            "大环内酯类结构相似性。",
            "避免大环内酯类，选用非大环内酯替代。",
        ),
        _allergy(
            "alg_aminoglycoside_cross",
            ["gentamicin", "庆大霉素"],
            ["tobramycin", "amikacin", "neomycin"],
            "medium",
            "氨基糖苷过敏患者使用其他氨基糖苷存在交叉过敏风险。",
            "氨基糖苷类结构相似性。",
            "避免氨基糖苷类，选用替代抗菌方案。",
        ),
        _allergy(
            "alg_quinolone_cross",
            ["ciprofloxacin", "环丙沙星"],
            ["levofloxacin", "moxifloxacin"],
            "medium",
            "喹诺酮过敏患者使用其他喹诺酮存在交叉过敏风险。",
            "喹诺酮类结构相似性。",
            "避免喹诺酮类，选用替代抗菌方案。",
        ),
        _allergy(
            "alg_aromatic_antiepileptic",
            ["phenytoin", "苯妥英"],
            ["carbamazepine", "phenobarbital", "lamotrigine"],
            "high",
            "芳香族抗癫痫药过敏患者使用其他芳香族抗癫痫药存在 DRESS 交叉风险。",
            "芳香族抗癫痫药交叉致敏。",
            "避免芳香族抗癫痫药交叉使用，选用结构不同替代。",
        ),
        _allergy(
            "alg_allopurinol_febuxostat",
            ["allopurinol", "别嘌醇"],
            ["febuxostat"],
            "low",
            "别嘌醇过敏患者使用非布司他交叉过敏概率较低。",
            "不同靶点，交叉反应率低。",
            "可在监测下评估非布司他。",
        ),
        _allergy(
            "alg_heparin_lmwh",
            ["heparin", "肝素"],
            ["enoxaparin", "dalteparin"],
            "high",
            "肝素过敏患者使用低分子肝素存在交叉过敏风险。",
            "同类抗凝药交叉反应。",
            "避免肝素类，评估 DOAC 或其他抗凝方案。",
        ),
        _allergy(
            "alg_animal_insulin",
            ["insulin porcine", "insulin bovine", "猪胰岛素", "牛胰岛素"],
            ["insulin glargine", "insulin lispro", "insulin aspart"],
            "medium",
            "动物源胰岛素过敏患者使用人胰岛素类似物存在低度交叉过敏风险。",
            "胰岛素蛋白结构差异导致交叉反应。",
            "优先人胰岛素类似物并在监测下使用。",
        ),
        _allergy(
            "alg_acetaminophen_propacetamol",
            ["acetaminophen", "对乙酰氨基酚", "paracetamol"],
            ["propacetamol"],
            "high",
            "对乙酰氨基酚过敏患者使用丙帕他莫（前药）存在过敏风险。",
            "丙帕他莫代谢为对乙酰氨基酚。",
            "避免丙帕他莫，选用非对乙酰氨基酚镇痛方案。",
        ),
    ]


def build_interaction_rules() -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []

    # ── Cardiology ──
    rules.append(
        _interaction(
            "ddi_digoxin_furosemide",
            ["digoxin", "furosemide"],
            "high",
            "地高辛与呋塞米联用可因低钾血症增加地高辛中毒风险。",
            "利尿剂致低钾→地高辛毒性增加。",
            "监测血钾和地高辛浓度，必要时补钾。",
            department="cardiology",
        )
    )
    rules.append(
        _interaction(
            "ddi_digoxin_amiodarone",
            ["digoxin", "amiodarone"],
            "high",
            "胺碘酮可显著升高地高辛浓度（约翻倍）。",
            "P-gp 抑制减少地高辛清除。",
            "地高辛减量50%并监测浓度。",
            department="cardiology",
        )
    )
    rules.extend(
        _pairwise_interactions(
            ACE_INHIBITORS,
            ["spironolactone"],
            rule_id_prefix="ddi_acei_spironolactone",
            risk_level="high",
            summary="ACEI 与螺内酯联用可致高钾血症。",
            mechanism="保钾机制叠加。",
            recommendation="监测血钾，必要时调整剂量或停用。",
            department="cardiology",
        )
    )
    rules.extend(
        _pairwise_interactions(
            ACE_INHIBITORS,
            ARBS,
            rule_id_prefix="ddi_acei_arb_dual",
            risk_level="high",
            summary="ACEI 与 ARB 双重 RAAS 阻断可致高钾血症和急性肾损伤。",
            mechanism="双重肾素-血管紧张素系统阻断。",
            recommendation="避免 ACEI+ARB 联合，除非有明确专科指征。",
            department="cardiology",
        )
    )
    rules.extend(
        _pairwise_interactions(
            BETA_BLOCKERS,
            CCB_NON_DHP,
            rule_id_prefix="ddi_bb_ccb",
            risk_level="high",
            summary="β 阻滞剂与非二氢吡啶类钙拮抗剂联用可致严重心动过缓、传导阻滞或心衰。",
            mechanism="负性 chronotropic/inotropic 叠加。",
            recommendation="避免联用或严密心电监测。",
            department="cardiology",
        )
    )
    rules.append(
        _interaction(
            "ddi_clopidogrel_omeprazole",
            ["clopidogrel", "omeprazole"],
            "high",
            "奥美拉唑抑制 CYP2C19，可显著降低氯吡格雷抗血小板活性。",
            "CYP2C19 抑制→氯吡格雷活性代谢物减少。",
            "换用泮托拉唑或 H2 受体拮抗剂。",
            department="cardiology",
        )
    )
    rules.append(
        _interaction(
            "ddi_warfarin_amiodarone",
            ["warfarin", "amiodarone"],
            "high",
            "胺碘酮抑制 CYP2C9，可致华法林 INR 显著升高。",
            "CYP2C9 抑制减少华法林代谢。",
            "华法林减量30-50%并加强 INR 监测。",
            department="cardiology",
        )
    )
    rules.extend(
        _pairwise_interactions(
            DOACS,
            NSAIDS,
            rule_id_prefix="ddi_doac_nsaids",
            risk_level="high",
            summary="DOAC 与 NSAIDs 联用出血风险显著增加。",
            mechanism="抗凝与 NSAIDs 胃肠道/全身出血风险叠加。",
            recommendation="避免联用，优先对乙酰氨基酚。",
            department="cardiology",
        )
    )
    rules.extend(
        _pairwise_interactions(
            DOACS,
            SSRIS,
            rule_id_prefix="ddi_doac_ssri",
            risk_level="medium",
            summary="DOAC 与 SSRI 联用出血风险增加。",
            mechanism="SSRI 抗血小板效应与 DOAC 抗凝叠加。",
            recommendation="评估获益风险，监测出血体征。",
            department="cardiology",
        )
    )
    rules.append(
        _interaction(
            "ddi_statin_cyclosporine",
            ["simvastatin", "cyclosporine"],
            "high",
            "环孢素与辛伐他汀联用横纹肌溶解风险显著增加。",
            "CYP3A4 及 OATP1B1 抑制→他汀暴露升高。",
            "避免联用或换用不经 CYP3A4 的他汀。",
            department="cardiology",
        )
    )
    rules.extend(
        _pairwise_interactions(
            ["clopidogrel"],
            PPI_WEAK,
            rule_id_prefix="ddi_clopidogrel_ppi_weak",
            risk_level="medium",
            summary="氯吡格雷与 PPI 联用可能轻度降低氯吡格雷活性。",
            mechanism="CYP2C19 弱抑制。",
            recommendation="优先泮托拉唑，监测血小板功能。",
            department="cardiology",
        )
    )
    rules.append(
        _interaction(
            "ddi_amiodarone_simvastatin",
            ["amiodarone", "simvastatin"],
            "high",
            "胺碘酮与辛伐他汀联用横纹肌溶解风险增加。",
            "CYP3A4 抑制→辛伐他汀暴露升高。",
            "辛伐他汀剂量限制≤20mg/天或换用其他他汀。",
            department="cardiology",
        )
    )
    rules.append(
        _interaction(
            "ddi_digoxin_clarithromycin",
            ["digoxin", "clarithromycin"],
            "high",
            "克拉霉素可升高地高辛浓度并降低肾清除。",
            "P-gp 抑制及肾清除降低。",
            "监测地高辛浓度，必要时减量。",
            department="cardiology",
        )
    )
    rules.append(
        _interaction(
            "ddi_digoxin_verapamil",
            ["digoxin", "verapamil"],
            "high",
            "维拉帕米可升高地高辛浓度。",
            "P-gp 抑制减少地高辛清除。",
            "地高辛减量并监测浓度。",
            department="cardiology",
        )
    )
    rules.extend(
        _pairwise_interactions(
            NITRATES,
            PDE5_INHIBITORS,
            rule_id_prefix="ddi_nitrate_pde5i",
            risk_level="high",
            summary="硝酸酯与 PDE5 抑制剂联用可致致命性低血压。",
            mechanism="协同扩血管。",
            recommendation="禁止联用，至少间隔24-48小时。",
            department="cardiology",
        )
    )
    rules.append(
        _interaction(
            "ddi_ticagrelor_simvastatin",
            ["ticagrelor", "simvastatin"],
            "high",
            "替格瑞洛与辛伐他汀>40mg 联用横纹肌溶解风险增加。",
            "CYP3A4 抑制→辛伐他汀暴露升高。",
            "辛伐他汀限制≤40mg/天。",
            department="cardiology",
        )
    )
    rules.extend(
        _pairwise_interactions(
            ["aspirin"],
            SSRIS,
            rule_id_prefix="ddi_aspirin_ssri",
            risk_level="medium",
            summary="阿司匹林与 SSRI 联用出血风险增加。",
            mechanism="SSRI 抗血小板效应叠加。",
            recommendation="评估获益风险，考虑 PPI 保护。",
            department="cardiology",
        )
    )
    rules.extend(
        _pairwise_interactions(
            ["heparin", "enoxaparin"],
            SSRIS,
            rule_id_prefix="ddi_heparin_ssri",
            risk_level="medium",
            summary="肝素/低分子肝素与 SSRI 联用出血风险增加。",
            mechanism="抗凝与 SSRI 抗血小板效应叠加。",
            recommendation="监测出血体征和血红蛋白。",
            department="cardiology",
        )
    )
    rules.extend(
        _pairwise_interactions(
            ["sotalol"],
            QT_PROLONGING,
            rule_id_prefix="ddi_sotalol_qt",
            risk_level="high",
            summary="索他洛尔与 QT 延长药物联用可致尖端扭转室速。",
            mechanism="QT 间期延长叠加。",
            recommendation="避免联用或严密 QT 监测。",
            department="cardiology",
            skip_same=True,
        )
    )

    # ── Endocrine ──
    rules.extend(
        _pairwise_interactions(
            ["insulin glargine", "insulin lispro", "insulin aspart"],
            SULFONYLUREAS,
            rule_id_prefix="ddi_insulin_sulfonylurea",
            risk_level="high",
            summary="胰岛素与磺脲类联用低血糖风险叠加。",
            mechanism="双重促胰岛素/降糖效应。",
            recommendation="加强血糖监测，调整剂量。",
            department="endocrine",
        )
    )
    rules.append(
        _interaction(
            "ddi_metformin_contrast",
            ["metformin", "iohexol"],
            "high",
            "二甲双胍与碘造影剂联用可致乳酸酸中毒。",
            "造影剂肾病→二甲双胍蓄积。",
            "造影前后暂停二甲双胍48-72小时。",
            department="endocrine",
        )
    )
    rules.extend(
        _pairwise_interactions(
            SGLT2_INHIBITORS,
            DIURETICS,
            rule_id_prefix="ddi_sglt2_diuretic",
            risk_level="medium",
            summary="SGLT2 抑制剂与利尿剂联用可致脱水和低血压。",
            mechanism="双重容量丢失。",
            recommendation="监测血压和容量状态。",
            department="endocrine",
        )
    )
    rules.append(
        _interaction(
            "ddi_levothyroxine_calcium",
            ["levothyroxine", "calcium carbonate"],
            "medium",
            "左甲状腺素与碳酸钙螯合降低 T4 吸收。",
            "金属离子螯合。",
            "间隔4小时以上服用。",
            department="endocrine",
        )
    )
    rules.append(
        _interaction(
            "ddi_levothyroxine_iron",
            ["levothyroxine", "ferrous sulfate"],
            "medium",
            "左甲状腺素与铁剂螯合降低 T4 吸收。",
            "金属离子螯合。",
            "间隔4小时以上服用。",
            department="endocrine",
        )
    )
    rules.extend(
        _pairwise_interactions(
            ["levothyroxine"],
            PPI_STRONG + PPI_WEAK,
            rule_id_prefix="ddi_levothyroxine_ppi",
            risk_level="medium",
            summary="左甲状腺素与 PPI 联用可能降低 T4 吸收。",
            mechanism="胃酸降低影响 T4 溶解吸收。",
            recommendation="监测 TSH，必要时调整左甲状腺素剂量。",
            department="endocrine",
        )
    )
    rules.extend(
        _pairwise_interactions(
            ["semaglutide", "liraglutide", "dulaglutide"],
            ["metformin", "glibenclamide", "warfarin"],
            rule_id_prefix="ddi_glp1_delayed_absorption",
            risk_level="medium",
            summary="GLP-1 激动剂延迟胃排空可影响口服药吸收。",
            mechanism="胃排空延迟改变口服药药代动力学。",
            recommendation="监测口服药疗效，必要时调整剂量。",
            department="endocrine",
        )
    )
    rules.append(
        _interaction(
            "ddi_metformin_alcohol",
            ["metformin", "alcohol"],
            "high",
            "二甲双胍与酒精联用乳酸酸中毒风险增加。",
            "酒精抑制糖异生+二甲双胍机制叠加。",
            "避免过量饮酒。",
            department="endocrine",
        )
    )
    rules.extend(
        _pairwise_interactions(
            SULFONYLUREAS,
            ["alcohol"],
            rule_id_prefix="ddi_sulfonylurea_alcohol",
            risk_level="medium",
            summary="磺脲类与酒精联用可致双硫仑样反应和低血糖。",
            mechanism="酒精干扰糖代谢并增强磺脲效应。",
            recommendation="避免饮酒，加强血糖监测。",
            department="endocrine",
        )
    )
    rules.append(
        _interaction(
            "ddi_acarbose_digestive_enzymes",
            ["acarbose", "pancreatin"],
            "low",
            "阿卡波糖与消化酶制剂联用降低阿卡波糖疗效。",
            "消化酶分解碳水化合物抵消阿卡波糖作用。",
            "避免同时服用。",
            department="endocrine",
        )
    )
    rules.extend(
        _pairwise_interactions(
            ["sitagliptin", "linagliptin", "saxagliptin"],
            ACE_INHIBITORS,
            rule_id_prefix="ddi_dpp4_acei",
            risk_level="medium",
            summary="DPP-4 抑制剂与 ACEI 联用血管性水肿风险增加。",
            mechanism="双重缓激肽降解抑制。",
            recommendation="监测血管性水肿体征。",
            department="endocrine",
        )
    )
    rules.append(
        _interaction(
            "ddi_pioglitazone_insulin",
            ["pioglitazone", "insulin glargine"],
            "medium",
            "吡格列酮与胰岛素联用水肿和心衰风险增加。",
            "TZD 水钠潴留+胰岛素叠加。",
            "监测体重、水肿和心衰症状。",
            department="endocrine",
        )
    )

    # ── Neurology ──
    rules.append(
        _interaction(
            "ddi_valproate_phenytoin",
            ["valproic acid", "phenytoin"],
            "high",
            "丙戊酸与苯妥英联用可因蛋白结合置换升高游离苯妥英。",
            "蛋白结合置换+代谢相互作用。",
            "监测游离苯妥英浓度，调整剂量。",
            department="neurology",
        )
    )
    rules.extend(
        _pairwise_interactions(
            ["carbamazepine"],
            CYP3A4_INHIBITORS,
            rule_id_prefix="ddi_carbamazepine_cyp3a4i",
            risk_level="high",
            summary="CYP3A4 抑制剂可致卡马西平中毒（共济失调、复视）。",
            mechanism="CYP3A4 抑制减少卡马西平代谢。",
            recommendation="监测卡马西平浓度，必要时减量。",
            department="neurology",
            skip_same=True,
        )
    )
    rules.extend(
        _pairwise_interactions(
            ["phenobarbital"],
            ["warfarin", "levothyroxine", "oral contraceptive"],
            rule_id_prefix="ddi_phenobarbital_inducer",
            risk_level="high",
            summary="苯巴比妥为强 CYP 诱导剂，可显著降低合用药物浓度。",
            mechanism="CYP 酶诱导加速合用药物代谢。",
            recommendation="监测合用药物疗效，必要时增加剂量。",
            department="neurology",
        )
    )
    rules.extend(
        _pairwise_interactions(
            SSRIS,
            ["tramadol"],
            rule_id_prefix="ddi_ssri_tramadol",
            risk_level="high",
            summary="SSRI 与曲马多联用可致 5-羟色胺综合征。",
            mechanism="5-HT 再摄取抑制+释放叠加。",
            recommendation="避免联用，换用非 5-HT 机制镇痛药。",
            department="neurology",
        )
    )
    rules.extend(
        _pairwise_interactions(
            SSRIS,
            TRIPTANS,
            rule_id_prefix="ddi_ssri_triptan",
            risk_level="high",
            summary="SSRI 与曲坦类联用可致 5-羟色胺综合征。",
            mechanism="5-HT 受体/再摄取双重作用。",
            recommendation="避免联用或严密监测 5-HT 综合征体征。",
            department="neurology",
        )
    )
    rules.extend(
        _pairwise_interactions(
            SSRIS,
            ["linezolid"],
            rule_id_prefix="ddi_ssri_linezolid",
            risk_level="high",
            summary="SSRI 与利奈唑胺联用可致 5-羟色胺综合征。",
            mechanism="利奈唑胺弱 MAO 抑制+SSRI 叠加。",
            recommendation="避免联用，换用非 MAO 抑制抗菌药。",
            department="neurology",
        )
    )
    rules.extend(
        _pairwise_interactions(
            SSRIS,
            MAO_INHIBITORS,
            rule_id_prefix="ddi_ssri_maoi",
            risk_level="high",
            summary="SSRI 与 MAO 抑制剂联用可致致命性 5-羟色胺综合征。",
            mechanism="5-HT 代谢双重阻断。",
            recommendation="禁止联用，需 MAO 抑制剂洗脱期。",
            department="neurology",
        )
    )
    rules.extend(
        _pairwise_interactions(
            OPIOIDS,
            BENZODIAZEPINES,
            rule_id_prefix="ddi_opioid_benzo",
            risk_level="high",
            summary="阿片类与苯二氮卓联用可致严重呼吸抑制（FDA 黑框警告）。",
            mechanism="中枢呼吸抑制叠加。",
            recommendation="避免联用，除非无替代且严密监测。",
            department="neurology",
        )
    )
    rules.extend(
        _pairwise_interactions(
            ["gabapentin", "pregabalin"],
            OPIOIDS,
            rule_id_prefix="ddi_gabapentinoid_opioid",
            risk_level="high",
            summary="加巴喷丁/普瑞巴林与阿片类联用呼吸抑制风险叠加。",
            mechanism="中枢抑制叠加。",
            recommendation="避免联用或减量并监测呼吸。",
            department="neurology",
        )
    )
    rules.append(
        _interaction(
            "ddi_levothyroxine_phenytoin",
            ["levothyroxine", "phenytoin"],
            "medium",
            "苯妥英加速左甲状腺素代谢，可致 TSH 升高。",
            "CYP 诱导及 T4 代谢加速。",
            "监测 TSH，必要时增加左甲状腺素剂量。",
            department="neurology",
        )
    )
    rules.append(
        _interaction(
            "ddi_valproate_lamotrigine",
            ["valproic acid", "lamotrigine"],
            "high",
            "丙戊酸抑制拉莫三嗪代谢，SJS/TEN 风险显著增加。",
            "UGT 抑制→拉莫三嗪浓度翻倍。",
            "拉莫三嗪剂量减半并缓慢滴定。",
            department="neurology",
        )
    )
    rules.append(
        _interaction(
            "ddi_carbamazepine_valproate",
            ["carbamazepine", "valproic acid"],
            "medium",
            "卡马西平诱导 CYP 酶降低丙戊酸浓度。",
            "CYP 诱导加速丙戊酸代谢。",
            "监测丙戊酸浓度，必要时调整剂量。",
            department="neurology",
        )
    )
    rules.extend(
        _pairwise_interactions(
            ANTIEPILEPTIC_INDUCERS,
            ["ethinyl estradiol", "levonorgestrel"],
            rule_id_prefix="ddi_antiepileptic_ocp",
            risk_level="high",
            summary="酶诱导抗癫痫药降低口服避孕药浓度，可致避孕失败。",
            mechanism="CYP 诱导加速甾体激素代谢。",
            recommendation="换用非激素避孕或增加雌激素剂量。",
            department="neurology",
        )
    )
    rules.append(
        _interaction(
            "ddi_lithium_nsaids",
            ["lithium", "ibuprofen"],
            "high",
            "NSAIDs 降低锂肾清除，可致锂中毒。",
            "前列腺素抑制减少锂排泄。",
            "避免 NSAIDs，监测锂浓度。",
            department="neurology",
        )
    )

    # ── Gastroenterology ──
    rules.append(
        _interaction(
            "ddi_omeprazole_methotrexate",
            ["omeprazole", "methotrexate"],
            "high",
            "PPI 减少甲氨蝶呤清除，高剂量 MTX 时毒性风险增加。",
            "肾小管转运体抑制延迟 MTX 排泄。",
            "高剂量 MTX 时避免 PPI 或换用 H2RA。",
            department="gastroenterology",
        )
    )
    rules.append(
        _interaction(
            "ddi_methotrexate_nsaids_gi",
            ["methotrexate", "ibuprofen"],
            "high",
            "NSAIDs 减少甲氨蝶呤肾清除，可致 MTX 毒性。",
            "肾清除竞争减少 MTX 排泄。",
            "避免 NSAIDs，监测 MTX 浓度和血常规。",
            department="gastroenterology",
        )
    )
    rules.append(
        _interaction(
            "ddi_sucralfate_quinolone",
            ["sucralfate", "ciprofloxacin"],
            "medium",
            "硫糖铝螯合喹诺酮降低其吸收。",
            "金属离子螯合。",
            "间隔2小时以上服用。",
            department="gastroenterology",
        )
    )
    rules.append(
        _interaction(
            "ddi_metoclopramide_anticholinergic",
            ["metoclopramide", "oxybutynin"],
            "medium",
            "甲氧氯普胺与抗胆碱能药药理拮抗。",
            "促动力 vs 抗胆碱能。",
            "避免联用，评估单一方案。",
            department="gastroenterology",
        )
    )
    rules.append(
        _interaction(
            "ddi_ursodeoxycholic_acid_antacid",
            ["ursodeoxycholic acid", "aluminum hydroxide"],
            "low",
            "抗酸剂螯合熊去氧胆酸降低其吸收。",
            "金属离子螯合。",
            "间隔2小时以上服用。",
            department="gastroenterology",
        )
    )
    rules.append(
        _interaction(
            "ddi_ibrutinib_ppi",
            ["ibrutinib", "omeprazole"],
            "medium",
            "PPI 降低依鲁替尼吸收。",
            "胃酸降低影响吸收。",
            "换用 H2RA 或短效抗酸剂。",
            department="gastroenterology",
        )
    )
    rules.append(
        _interaction(
            "ddi_mycophenolate_ppi",
            ["mycophenolate", "omeprazole"],
            "medium",
            "PPI 降低吗替麦考酚酯吸收。",
            "胃酸降低影响 MPA 吸收。",
            "监测 MPA 浓度或换用 H2RA。",
            department="gastroenterology",
        )
    )

    # ── Nephrology ──
    rules.extend(
        _pairwise_interactions(
            ACE_INHIBITORS,
            POTASSIUM_SUPPLEMENTS,
            rule_id_prefix="ddi_acei_potassium",
            risk_level="high",
            summary="ACEI 与钾补充剂联用可致高钾血症。",
            mechanism="保钾机制叠加。",
            recommendation="监测血钾，避免不必要的钾补充。",
            department="nephrology",
        )
    )
    rules.extend(
        _pairwise_interactions(
            ACE_INHIBITORS,
            ["sulfamethoxazole"],
            rule_id_prefix="ddi_acei_tmp_smx",
            risk_level="high",
            summary="ACEI 与复方磺胺甲噁唑联用可致高钾血症。",
            mechanism="TMP 保钾+ACEI 保钾叠加。",
            recommendation="监测血钾，必要时停用。",
            department="nephrology",
        )
    )
    rules.extend(
        _pairwise_interactions(
            ARBS,
            POTASSIUM_SUPPLEMENTS,
            rule_id_prefix="ddi_arb_potassium",
            risk_level="high",
            summary="ARB 与钾补充剂联用可致高钾血症。",
            mechanism="保钾机制叠加。",
            recommendation="监测血钾。",
            department="nephrology",
        )
    )
    rules.extend(
        _pairwise_interactions(
            NSAIDS,
            ACE_INHIBITORS + ARBS,
            rule_id_prefix="ddi_nsaids_raas",
            risk_level="high",
            summary="NSAIDs 与 ACEI/ARB 联用可致急性肾损伤（三联打击）。",
            mechanism="前列腺素抑制+RAAS 阻断→肾灌注下降。",
            recommendation="避免三联，监测肾功能。",
            department="nephrology",
        )
    )
    rules.extend(
        _pairwise_interactions(
            AMINOGLYCOSIDES,
            ["vancomycin"],
            rule_id_prefix="ddi_aminoglycoside_vancomycin",
            risk_level="high",
            summary="氨基糖苷类与万古霉素联用肾毒性叠加。",
            mechanism="肾小管毒性叠加。",
            recommendation="避免联用或严密监测肾功能。",
            department="nephrology",
        )
    )
    rules.append(
        _interaction(
            "ddi_cyclosporine_nsaids",
            ["cyclosporine", "ibuprofen"],
            "high",
            "环孢素与 NSAIDs 联用肾毒性叠加。",
            "肾血管收缩+NSAIDs 肾毒性。",
            "避免联用，监测肾功能。",
            department="nephrology",
        )
    )
    rules.extend(
        _pairwise_interactions(
            ["furosemide"],
            AMINOGLYCOSIDES,
            rule_id_prefix="ddi_furosemide_aminoglycoside",
            risk_level="high",
            summary="呋塞米与氨基糖苷类联用耳毒性叠加。",
            mechanism="利尿剂致内耳离子紊乱+氨基糖苷耳毒性。",
            recommendation="避免联用或监测听力。",
            department="nephrology",
        )
    )
    rules.append(
        _interaction(
            "ddi_sevelamer_oral_drugs",
            ["sevelamer", "levothyroxine"],
            "medium",
            "司维拉姆吸附其他口服药物降低其吸收。",
            "磷酸盐结合剂非特异性吸附。",
            "间隔1小时以上服用。",
            department="nephrology",
        )
    )

    # ── Hematology ──
    rules.append(
        _interaction(
            "ddi_warfarin_fluconazole",
            ["warfarin", "fluconazole"],
            "high",
            "氟康唑抑制 CYP2C9，可致华法林 INR 显著升高。",
            "CYP2C9 抑制。",
            "华法林减量并加强 INR 监测。",
            department="hematology",
        )
    )
    rules.append(
        _interaction(
            "ddi_warfarin_metronidazole",
            ["warfarin", "metronidazole"],
            "high",
            "甲硝唑抑制 CYP2C9，可致华法林 INR 升高。",
            "CYP2C9 抑制。",
            "华法林减量并加强 INR 监测。",
            department="hematology",
        )
    )
    rules.extend(
        _pairwise_interactions(
            ["clopidogrel"],
            DOACS + ["warfarin", "heparin"],
            rule_id_prefix="ddi_clopidogrel_anticoagulant",
            risk_level="high",
            summary="氯吡格雷与抗凝剂联用出血风险叠加。",
            mechanism="抗血小板+抗凝双重作用。",
            recommendation="仅在明确指征下联用并严密监测。",
            department="hematology",
        )
    )
    rules.append(
        _interaction(
            "ddi_methotrexate_tmp_smx",
            ["methotrexate", "sulfamethoxazole"],
            "high",
            "甲氨蝶呤与复方磺胺甲噁唑联用骨髓抑制风险叠加。",
            "叶酸拮抗叠加。",
            "避免联用，换用非磺胺抗菌药。",
            department="hematology",
        )
    )
    rules.append(
        _interaction(
            "ddi_methotrexate_ppi",
            ["methotrexate", "omeprazole"],
            "high",
            "PPI 延迟甲氨蝶呤清除，高剂量 MTX 时毒性增加。",
            "H+/K+ ATPase 抑制减少 MTX 排泄。",
            "高剂量 MTX 时避免 PPI。",
            department="hematology",
        )
    )
    rules.append(
        _interaction(
            "ddi_ibrutinib_warfarin",
            ["ibrutinib", "warfarin"],
            "high",
            "依鲁替尼与华法林联用出血风险增加。",
            "BTK 抑制+抗凝叠加。",
            "避免联用，优先 DOAC。",
            department="hematology",
        )
    )
    rules.append(
        _interaction(
            "ddi_lenalidomide_erythropoietin",
            ["lenalidomide", "epoetin alfa"],
            "high",
            "来那度胺与 EPO 联用血栓风险叠加。",
            "双重促血栓机制。",
            "评估血栓预防必要性。",
            department="hematology",
        )
    )
    rules.append(
        _interaction(
            "ddi_doxorubicin_verapamil",
            ["doxorubicin", "verapamil"],
            "high",
            "维拉帕米抑制 P-gp 增加多柔比星毒性。",
            "P-gp 抑制→多柔比星蓄积。",
            "避免联用或严密监测心脏毒性。",
            department="hematology",
        )
    )

    # ── Rheumatology ──
    rules.append(
        _interaction(
            "ddi_methotrexate_leflunomide",
            ["methotrexate", "leflunomide"],
            "high",
            "甲氨蝶呤与来氟米特联用肝毒性叠加。",
            "双重免疫抑制及肝毒性。",
            "严密监测肝功能，避免不必要的联合。",
            department="rheumatology",
        )
    )
    rules.append(
        _interaction(
            "ddi_azathioprine_allopurinol",
            ["azathioprine", "allopurinol"],
            "high",
            "别嘌醇抑制黄嘌呤氧化酶，可致硫唑嘌呤毒性致命。",
            "6-MP 代谢受阻→骨髓抑制。",
            "硫唑嘌呤剂量减至25-33%或换用其他方案。",
            department="rheumatology",
        )
    )
    rules.append(
        _interaction(
            "ddi_cyclosporine_methotrexate",
            ["cyclosporine", "methotrexate"],
            "high",
            "环孢素与甲氨蝶呤联用免疫抑制及肾毒性叠加。",
            "双重免疫抑制+肾毒性。",
            "严密监测血常规和肾功能。",
            department="rheumatology",
        )
    )
    rules.append(
        _interaction(
            "ddi_hcq_tamoxifen",
            ["hydroxychloroquine", "tamoxifen"],
            "medium",
            "羟氯喹与他莫昔芬联用视网膜毒性叠加。",
            "双重视网膜毒性风险。",
            "加强眼科监测。",
            department="rheumatology",
        )
    )
    rules.append(
        _interaction(
            "ddi_tnf_live_vaccine",
            ["adalimumab", "infliximab"],
            ["bcg vaccine", "yellow fever vaccine"],
            "high",
            "TNF 抑制剂与活疫苗联用可致疫苗相关感染。",
            "免疫抑制状态下活疫苗复制。",
            "避免活疫苗，使用灭活疫苗。",
            department="rheumatology",
        )
    )
    rules.append(
        _interaction(
            "ddi_cyclophosphamide_allopurinol",
            ["cyclophosphamide", "allopurinol"],
            "medium",
            "环磷酰胺与别嘌醇联用骨髓抑制风险增加。",
            "代谢相互作用增加骨髓抑制。",
            "严密监测血常规。",
            department="rheumatology",
        )
    )
    rules.extend(
        _pairwise_interactions(
            ["colchicine"],
            CYP3A4_INHIBITORS,
            rule_id_prefix="ddi_colchicine_cyp3a4i",
            risk_level="high",
            summary="CYP3A4 抑制剂可致秋水仙碱中毒（可致命）。",
            mechanism="CYP3A4 及 P-gp 抑制→秋水仙碱蓄积。",
            recommendation="避免联用或秋水仙碱大幅减量。",
            department="rheumatology",
            skip_same=True,
        )
    )

    # ── Infectious diseases ──
    rules.append(
        _interaction(
            "ddi_rifampin_oral_contraceptives",
            ["rifampin", "ethinyl estradiol"],
            "high",
            "利福平强诱导 CYP 酶，可致口服避孕药失效。",
            "CYP3A4 诱导加速激素代谢。",
            "换用非激素避孕或增加雌激素剂量。",
            department="infectious_diseases",
        )
    )
    rules.append(
        _interaction(
            "ddi_rifampin_warfarin",
            ["rifampin", "warfarin"],
            "high",
            "利福平诱导 CYP 酶，可致华法林 INR 显著降低。",
            "CYP 诱导加速华法林代谢。",
            "华法林增量并加强 INR 监测。",
            department="infectious_diseases",
        )
    )
    rules.append(
        _interaction(
            "ddi_clarithromycin_colchicine",
            ["clarithromycin", "colchicine"],
            "high",
            "克拉霉素抑制 CYP3A4 和 P-gp，可致秋水仙碱中毒。",
            "双重转运/代谢抑制。",
            "避免联用。",
            department="infectious_diseases",
        )
    )
    rules.extend(
        _pairwise_interactions(
            ["voriconazole", "fluconazole"],
            STATINS,
            rule_id_prefix="ddi_azole_statins",
            risk_level="high",
            summary="唑类抗真菌药与他汀联用横纹肌溶解风险增加。",
            mechanism="CYP3A4 抑制→他汀暴露升高。",
            recommendation="暂停他汀或换用不经 CYP3A4 的他汀。",
            department="infectious_diseases",
        )
    )
    rules.append(
        _interaction(
            "ddi_ganciclovir_myelotoxic",
            ["ganciclovir", "azathioprine"],
            "high",
            "更昔洛韦与骨髓抑制药联用骨髓毒性叠加。",
            "双重骨髓抑制。",
            "严密监测血常规。",
            department="infectious_diseases",
        )
    )
    rules.append(
        _interaction(
            "ddi_amphotericin_b_nephrotoxic",
            ["amphotericin b", "gentamicin"],
            "high",
            "两性霉素B与肾毒性药联用肾毒性叠加。",
            "肾小管毒性叠加。",
            "避免联用或严密监测肾功能。",
            department="infectious_diseases",
        )
    )
    rules.append(
        _interaction(
            "ddi_isoniazid_phenytoin",
            ["isoniazid", "phenytoin"],
            "high",
            "异烟肼抑制 CYP2C9，可致苯妥英中毒。",
            "CYP2C9 抑制。",
            "监测苯妥英浓度，必要时减量。",
            department="infectious_diseases",
        )
    )
    rules.append(
        _interaction(
            "ddi_arv_ppi",
            ["atazanavir", "omeprazole"],
            "high",
            "HIV 蛋白酶抑制剂与 PPI 联用可致抗 HIV 失败。",
            "胃酸降低影响 PI 吸收。",
            "换用 H2RA 或抗酸剂。",
            department="infectious_diseases",
        )
    )
    rules.extend(
        _pairwise_interactions(
            ["fluconazole"],
            QT_PROLONGING,
            rule_id_prefix="ddi_fluconazole_qt",
            risk_level="high",
            summary="氟康唑与 QT 延长药物联用可致尖端扭转室速。",
            mechanism="QT 间期延长叠加。",
            recommendation="避免联用或严密 QT 监测。",
            department="infectious_diseases",
            skip_same=True,
        )
    )

    # ── Psychiatry ──
    rules.append(
        _interaction(
            "ddi_lithium_acei",
            ["lithium", "lisinopril"],
            "high",
            "ACEI 降低锂肾清除，可致锂中毒。",
            "RAAS 抑制减少锂排泄。",
            "监测锂浓度，必要时减量。",
            department="psychiatry",
        )
    )
    rules.append(
        _interaction(
            "ddi_lithium_diuretics",
            ["lithium", "hydrochlorothiazide"],
            "high",
            "噻嗪类利尿剂可致锂中毒（钠丢失→锂重吸收增加）。",
            "容量丢失增加近端锂重吸收。",
            "监测锂浓度，必要时减量。",
            department="psychiatry",
        )
    )
    rules.append(
        _interaction(
            "ddi_maoi_tyramine",
            ["phenelzine", "tyramine"],
            "high",
            "MAO 抑制剂与含酪胺食物联用可致高血压危象。",
            "酪胺蓄积→儿茶酚胺释放。",
            "严格低酪胺饮食。",
            department="psychiatry",
        )
    )
    rules.extend(
        _pairwise_interactions(
            ["clozapine"],
            ["fluvoxamine", "ciprofloxacin"],
            rule_id_prefix="ddi_clozapine_cyp1a2i",
            risk_level="high",
            summary="CYP1A2 抑制剂可致氯氮平中毒（癫痫/粒细胞缺乏）。",
            mechanism="CYP1A2 抑制→氯氮平浓度升高。",
            recommendation="氯氮平减量并监测浓度。",
            department="psychiatry",
        )
    )
    rules.extend(
        _pairwise_interactions(
            ANTIPSYCHOTICS,
            QT_PROLONGING,
            rule_id_prefix="ddi_antipsychotic_qt",
            risk_level="high",
            summary="抗精神病药与 QT 延长药物联用可致尖端扭转室速。",
            mechanism="QT 间期延长叠加。",
            recommendation="避免联用或严密 QT 监测。",
            department="psychiatry",
            skip_same=True,
        )
    )
    rules.extend(
        _pairwise_interactions(
            SSRIS,
            TCAS,
            rule_id_prefix="ddi_ssri_tca",
            risk_level="high",
            summary="SSRI 抑制 CYP2D6 可致三环抗抑郁药中毒。",
            mechanism="CYP2D6 抑制→TCA 浓度升高。",
            recommendation="避免联用或 TCA 大幅减量。",
            department="psychiatry",
        )
    )
    rules.append(
        _interaction(
            "ddi_carbamazepine_clozapine",
            ["carbamazepine", "clozapine"],
            "high",
            "卡马西平与氯氮平联用骨髓抑制及 CYP 诱导风险。",
            "CYP 诱导+骨髓抑制叠加。",
            "避免联用，严密监测血常规。",
            department="psychiatry",
        )
    )
    rules.append(
        _interaction(
            "ddi_valproate_aspirin",
            ["valproic acid", "aspirin"],
            "medium",
            "阿司匹林与丙戊酸联用可因蛋白结合置换升高游离丙戊酸。",
            "蛋白结合置换。",
            "监测丙戊酸浓度，必要时减量。",
            department="psychiatry",
        )
    )

    # ── Geriatrics composite ──
    rules.extend(
        _pairwise_interactions(
            BENZODIAZEPINES,
            OPIOIDS,
            rule_id_prefix="ddi_geriatrics_fall_opioid_benzo",
            risk_level="high",
            summary="老年患者苯二氮卓与阿片类联用跌倒及呼吸抑制风险极高。",
            mechanism="中枢抑制+平衡障碍。",
            recommendation="避免联用，评估非镇静替代。",
            department="geriatrics",
        )
    )
    rules.extend(
        _pairwise_interactions(
            BENZODIAZEPINES,
            ANTIHYPERTENSIVES_FALL,
            rule_id_prefix="ddi_geriatrics_fall_benzo_bp",
            risk_level="high",
            summary="老年患者苯二氮卓与降压药联用跌倒风险增加。",
            mechanism="镇静+直立低血压。",
            recommendation="评估跌倒风险，考虑减药。",
            department="geriatrics",
        )
    )
    rules.extend(
        _pairwise_interactions(
            BENZODIAZEPINES,
            DIURETICS,
            rule_id_prefix="ddi_geriatrics_fall_benzo_diuretic",
            risk_level="high",
            summary="老年患者苯二氮卓与利尿剂联用跌倒风险增加（跌倒四联组分）。",
            mechanism="镇静+直立低血压/电解质紊乱。",
            recommendation="评估跌倒风险，考虑减药。",
            department="geriatrics",
        )
    )
    rules.extend(
        _within_group_pairwise(
            ANTICHOLINERGICS[:4],
            rule_id_prefix="ddi_geriatrics_anticholinergic_burden",
            risk_level="medium",
            summary="多种抗胆碱能药联用增加老年患者抗胆碱能负荷。",
            mechanism="抗胆碱能效应叠加。",
            recommendation="评估抗胆碱能负荷，考虑减药或换用低负担替代。",
            department="geriatrics",
        )
    )

    # ── ICU / Emergency ──
    rules.extend(
        _pairwise_interactions(
            ["norepinephrine"],
            MAO_INHIBITORS,
            rule_id_prefix="ddi_icu_norepi_maoi",
            risk_level="high",
            summary="去甲肾上腺素与 MAO 抑制剂联用可致高血压危象。",
            mechanism="儿茶酚胺蓄积。",
            recommendation="避免联用。",
            department="icu",
        )
    )
    rules.append(
        _interaction(
            "ddi_icu_propofol_lipid",
            ["propofol", "lipid emulsion"],
            "medium",
            "丙泊酚与脂肪乳联用可致脂肪超载综合征。",
            "脂质负荷叠加。",
            "监测甘油三酯和肝功能。",
            department="icu",
        )
    )
    rules.extend(
        _pairwise_interactions(
            ["midazolam", "propofol", "dexmedetomidine"],
            ["rocuronium", "vecuronium"],
            rule_id_prefix="ddi_icu_sedative_nmb",
            risk_level="high",
            summary="镇静剂与肌松药联用呼吸抑制风险叠加。",
            mechanism="中枢抑制+呼吸肌麻痹。",
            recommendation="严密呼吸监测，备拮抗剂。",
            department="icu",
        )
    )
    rules.append(
        _interaction(
            "ddi_icu_vasopressor_beta_blocker",
            ["norepinephrine", "propranolol"],
            "high",
            "血管加压药与 β 阻滞剂联用药理拮抗，血流动力学不稳定。",
            "α/β 受体效应拮抗。",
            "避免非选择性 β 阻滞剂，优先 β1 选择性。",
            department="icu",
        )
    )
    rules.append(
        _interaction(
            "ddi_icu_heparin_protamine",
            ["heparin", "protamine"],
            "low",
            "鱼精蛋白为肝素解毒剂，但本身可致过敏及低血压。",
            "肝素-鱼精蛋白复合物形成。",
            "按指南缓慢推注，监测过敏。",
            department="icu",
        )
    )
    rules.append(
        _interaction(
            "ddi_icu_naloxone_opioid",
            ["naloxone", "morphine"],
            "low",
            "纳洛酮为阿片类拮抗剂，快速逆转可致急性戒断。",
            "μ 受体竞争性拮抗。",
            "滴定给药，避免一次性大剂量。",
            department="icu",
        )
    )
    rules.append(
        _interaction(
            "ddi_icu_insulin_dextrose_potassium",
            ["insulin lispro", "dextrose", "potassium chloride"],
            "medium",
            "GIK 方案需严密监测血糖和血钾。",
            "胰岛素驱动钾内流+葡萄糖代谢。",
            "每小时监测血糖和血钾。",
            department="icu",
        )
    )
    rules.append(
        _interaction(
            "ddi_icu_vasopressin_norepinephrine",
            ["vasopressin", "norepinephrine"],
            "medium",
            "加压素与去甲肾上腺素联用外周缺血风险叠加。",
            "血管收缩叠加。",
            "监测末梢灌注和乳酸。",
            department="icu",
        )
    )

    return rules


STAGE9_DRUG_ALIASES: dict[str, list[str]] = {
    "isotretinoin": ["异维A酸", "维A酸"],
    "valproic acid": ["丙戊酸", "丙戊酸钠", "depakote"],
    "finasteride": ["非那雄胺", "保法止"],
    "ribavirin": ["利巴韦林"],
    "leflunomide": ["来氟米特", "爱若华"],
    "mycophenolate": ["吗替麦考酚酯", "骁悉"],
    "carbimazole": ["卡比马唑", "甲亢平"],
    "misoprostol": ["米索前列醇"],
    "ergotamine": ["麦角胺"],
    "cyclophosphamide": ["环磷酰胺"],
    "gold sodium thiomalate": ["金制剂", "硫代硫酸金钠"],
    "chloramphenicol": ["氯霉素"],
    "codeine": ["可待因"],
    "dextromethorphan": ["右美沙芬"],
    "iohexol": ["碘海醇", "造影剂"],
    "iopamidol": ["碘帕醇"],
    "iodixanol": ["碘克沙醇"],
    "propacetamol": ["丙帕他莫"],
    "febuxostat": ["非布司他"],
    "dalteparin": ["达肝素"],
    "empagliflozin": ["恩格列净"],
    "dapagliflozin": ["达格列净"],
    "canagliflozin": ["卡格列净"],
    "semaglutide": ["司美格鲁肽"],
    "liraglutide": ["利拉鲁肽"],
    "dulaglutide": ["度拉糖肽"],
    "sitagliptin": ["西格列汀"],
    "linagliptin": ["利格列汀"],
    "saxagliptin": ["沙格列汀"],
    "pioglitazone": ["吡格列酮"],
    "lamotrigine": ["拉莫三嗪"],
    "linezolid": ["利奈唑胺"],
    "phenelzine": ["苯乙肼"],
    "tranylcypromine": ["反苯环丙胺"],
    "isocarboxazid": ["异卡波肼"],
    "selegiline": ["司来吉兰"],
    "sumatriptan": ["舒马曲坦"],
    "rizatriptan": ["利扎曲坦"],
    "zolmitriptan": ["佐米曲坦"],
    "ethinyl estradiol": ["炔雌醇", "口服避孕药"],
    "levonorgestrel": ["左炔诺孕酮"],
    "calcium carbonate": ["碳酸钙"],
    "ferrous sulfate": ["硫酸亚铁"],
    "alcohol": ["乙醇", "酒精"],
    "pancreatin": ["胰酶", "得每通"],
    "sucralfate": ["硫糖铝"],
    "ursodeoxycholic acid": ["熊去氧胆酸", "优思弗"],
    "aluminum hydroxide": ["氢氧化铝"],
    "ibrutinib": ["依鲁替尼"],
    "sevelamer": ["司维拉姆"],
    "lenalidomide": ["来那度胺"],
    "epoetin alfa": ["促红细胞生成素", "EPO"],
    "doxorubicin": ["多柔比星", "阿霉素"],
    "hydroxychloroquine": ["羟氯喹", "赛能"],
    "tamoxifen": ["他莫昔芬"],
    "adalimumab": ["阿达木单抗"],
    "infliximab": ["英夫利西单抗"],
    "bcg vaccine": ["卡介苗"],
    "yellow fever vaccine": ["黄热病疫苗"],
    "colchicine": ["秋水仙碱"],
    "rifampin": ["利福平"],
    "ganciclovir": ["更昔洛韦"],
    "amphotericin b": ["两性霉素B"],
    "atazanavir": ["阿扎那韦"],
    "fluvoxamine": ["氟伏沙明"],
    "tyramine": ["酪胺"],
    "propofol": ["丙泊酚"],
    "lipid emulsion": ["脂肪乳"],
    "midazolam": ["咪达唑仑"],
    "dexmedetomidine": ["右美托咪定"],
    "rocuronium": ["罗库溴铵"],
    "vecuronium": ["维库溴铵"],
    "protamine": ["鱼精蛋白"],
    "naloxone": ["纳洛酮"],
    "dextrose": ["葡萄糖"],
    "potassium chloride": ["氯化钾"],
    "vasopressin": ["加压素"],
    "norepinephrine": ["去甲肾上腺素"],
    "apixaban": ["阿哌沙班"],
    "dabigatran": ["达比加群"],
    "rivaroxaban": ["利伐沙班"],
    "sildenafil": ["西地那非", "万艾可"],
    "tadalafil": ["他达拉非", "希爱力"],
    "nitroglycerin": ["硝酸甘油"],
    "isosorbide dinitrate": ["硝酸异山梨酯"],
    "isosorbide mononitrate": ["单硝酸异山梨酯"],
    "lithium": ["锂盐", "碳酸锂"],
    "methotrexate": ["甲氨蝶呤", "MTX"],
    "azathioprine": ["硫唑嘌呤"],
    "allopurinol": ["别嘌醇"],
    "cyclosporine": ["环孢素"],
    "sulfamethoxazole": ["磺胺甲噁唑", "复方磺胺"],
    "gentamicin": ["庆大霉素"],
    "tobramycin": ["妥布霉素"],
    "amikacin": ["阿米卡星"],
    "potassium citrate": ["枸橼酸钾"],
}


def get_curated_rules() -> dict[str, Any]:
    """Return all curated Stage 9 rules grouped by type."""
    population = build_population_rules()
    allergy = build_allergy_rules()
    interaction = build_interaction_rules()
    scenario = build_scenario_rules()
    return {
        "population_rules": population,
        "allergy_rules": allergy,
        "interaction_rules": interaction,
        "scenario_rules": scenario,
        "drug_aliases": STAGE9_DRUG_ALIASES,
        "meta": {
            "source": SOURCE,
            "population_count": len(population),
            "allergy_count": len(allergy),
            "interaction_count": len(interaction),
            "scenario_count": len(scenario),
        },
    }
