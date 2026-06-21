"""
规则引擎 — LLM 不可用时的硬编码关键相互作用规则

设计原则：
  1. 只覆盖「绝对不能漏掉」的高危相互作用（严重/禁忌级别）
  2. 规则来自权威来源，不与 KG 数据重复（但作为 KG 的硬兜底）
  3. 基于药物名称的精确匹配 + 模糊匹配
  4. 返回结构化结果，格式与 Graph RAG 工具一致

当 LLM API 不可用时，系统降级到此规则引擎，直接进行药物安全性检查。
"""
from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger("rule-engine")


# ============================================================
# 关键相互作用规则库
# ============================================================

# 格式: (drug_a_patterns, drug_b_patterns, severity, mechanism, effect, recommendation, evidence)
CRITICAL_INTERACTIONS = [
    # ---- 抗凝药 (Warfarin) 相关 ----
    (
        ["华法林", "warfarin", "华法林钠"],
        ["阿司匹林", "aspirin", "拜阿司匹林"],
        "severe",
        "协同抗凝+抑制血小板聚集",
        "显著增加出血风险（消化道、颅内）",
        "联合使用需严密监测INR。建议加用PPI保护胃黏膜",
        "A",
    ),
    (
        ["华法林", "warfarin", "华法林钠"],
        ["布洛芬", "ibuprofen", "芬必得", "美林", "双氯芬酸", "diclofenac", "扶他林",
         "萘普生", "naproxen", "塞来昔布", "celecoxib", "依托考昔"],
        "severe",
        "NSAIDs抑制血小板+损伤胃黏膜+可能置换华法林蛋白结合",
        "大幅增加消化道出血风险，INR可能升高",
        "避免联用。确需抗炎可选对乙酰氨基酚（常规剂量不影响INR）",
        "A",
    ),
    (
        ["华法林", "warfarin"],
        ["氯吡格雷", "clopidogrel", "波立维", "替格瑞洛", "ticagrelor"],
        "severe",
        "抗凝+抗血小板双重作用",
        "出血风险显著增加",
        "需在医生指导下评估获益/风险，通常用于特定适应症",
        "A",
    ),
    (
        ["华法林", "warfarin"],
        ["圣约翰草", "贯叶连翘", "路优泰", "St John's wort"],
        "severe",
        "圣约翰草强效诱导CYP3A4/CYP2C9，加速华法林代谢",
        "华法林血药浓度大幅下降→INR降低→血栓风险增加",
        "禁止联用",
        "A",
    ),
    (
        ["华法林", "warfarin"],
        ["维生素K", "vitamin K", "维生素K1"],
        "severe",
        "维生素K直接拮抗华法林抗凝作用",
        "华法林失效，INR下降，血栓风险增加",
        "华法林服药期间避免额外补充维生素K。绿叶蔬菜摄入量需保持恒定",
        "A",
    ),

    # ---- 他汀类 (Statins) 相关 ----
    (
        ["阿托伐他汀", "atorvastatin", "立普妥", "辛伐他汀", "simvastatin",
         "洛伐他汀", "lovastatin"],
        ["西柚", "葡萄柚", "grapefruit", "柚子"],
        "severe",
        "西柚中呋喃香豆素抑制肠道CYP3A4，大幅增加他汀生物利用度",
        "他汀血药浓度升高数倍→横纹肌溶解风险显著增加",
        "服用他汀期间禁止食用西柚/葡萄柚及其制品",
        "A",
    ),
    (
        ["阿托伐他汀", "atorvastatin", "辛伐他汀", "simvastatin"],
        ["克拉霉素", "clarithromycin", "红霉素", "erythromycin", "伊曲康唑",
         "itraconazole", "酮康唑", "ketoconazole", "氟康唑", "fluconazole"],
        "severe",
        "CYP3A4强抑制剂显著减慢他汀代谢",
        "他汀血药浓度大幅升高→肌病/横纹肌溶解风险",
        "避免联用。确需抗生素可选阿奇霉素（不影响CYP3A4）",
        "A",
    ),

    # ---- 降压药 + NSAIDs ----
    (
        ["卡托普利", "captopril", "依那普利", "enalapril", "贝那普利",
         "氯沙坦", "losartan", "缬沙坦", "valsartan", "厄贝沙坦", "irbesartan"],
        ["布洛芬", "ibuprofen", "双氯芬酸", "diclofenac", "萘普生", "naproxen",
         "吲哚美辛", "indomethacin"],
        "moderate",
        "NSAIDs抑制前列腺素合成→减弱ACEI/ARB降压效果+减少肾灌注",
        "血压控制恶化，肾功能可能下降",
        "短期使用通常安全。长期联用需监测血压和肾功能",
        "B",
    ),

    # ---- 氯吡格雷 + PPI ----
    (
        ["氯吡格雷", "clopidogrel", "波立维"],
        ["奥美拉唑", "omeprazole", "洛赛克", "埃索美拉唑", "esomeprazole"],
        "moderate",
        "奥美拉唑/埃索美拉唑抑制CYP2C19→减少氯吡格雷活性代谢物生成",
        "氯吡格雷抗血小板作用减弱→心血管事件风险增加",
        "改用泮托拉唑或雷贝拉唑（对CYP2C19影响最小）",
        "A",
    ),

    # ---- 二甲双胍 + 酒精 ----
    (
        ["二甲双胍", "metformin", "格华止"],
        ["酒精", "饮酒", "alcohol", "乙醇"],
        "moderate",
        "酒精增加二甲双胍相关的乳酸酸中毒风险",
        "乳酸酸中毒（罕见但可致命，死亡率约50%）",
        "服用二甲双胍期间限制或避免饮酒",
        "B",
    ),

    # ---- 对乙酰氨基酚 + 酒精 ----
    (
        ["对乙酰氨基酚", "扑热息痛", "泰诺", "acetaminophen", "paracetamol"],
        ["酒精", "饮酒", "alcohol"],
        "severe",
        "酒精诱导CYP2E1→增加NAPQI毒性代谢物生成",
        "肝毒性显著增加，即使常规剂量也可能导致严重肝损伤",
        "服药期间禁止饮酒。慢性饮酒者每日对乙酰氨基酚≤2g",
        "A",
    ),

    # ---- SSRI + 圣约翰草 (5-HT综合征) ----
    (
        ["氟西汀", "fluoxetine", "舍曲林", "sertraline", "帕罗西汀", "paroxetine",
         "西酞普兰", "citalopram", "艾司西酞普兰", "escitalopram"],
        ["圣约翰草", "贯叶连翘", "路优泰", "St John's wort"],
        "severe",
        "双方均增加5-HT能活性→叠加→5-HT综合征",
        "5-HT综合征：激越、高热、肌阵挛、意识障碍→可能危及生命",
        "禁止联用",
        "A",
    ),

    # ---- 苯二氮䓬类 + 酒精 ----
    (
        ["地西泮", "diazepam", "安定", "阿普唑仑", "alprazolam", "劳拉西泮",
         "lorazepam", "氯硝西泮", "clonazepam", "艾司唑仑", "estazolam"],
        ["酒精", "饮酒", "alcohol"],
        "severe",
        "酒精与苯二氮䓬类协同抑制中枢神经系统",
        "过度镇静→呼吸抑制→昏迷甚至死亡",
        "服药期间绝对禁止饮酒",
        "A",
    ),

    # ---- 氟喹诺酮类 + 乳制品 ----
    (
        ["左氧氟沙星", "levofloxacin", "可乐必妥", "莫西沙星", "moxifloxacin",
         "环丙沙星", "ciprofloxacin"],
        ["牛奶", "酸奶", "乳制品", "钙片", "dairy", "calcium"],
        "moderate",
        "二价/三价阳离子(Ca²⁺, Mg²⁺, Fe²⁺, Zn²⁺)与喹诺酮类螯合",
        "抗生素吸收减少→抗菌效果下降→治疗失败风险",
        "服药前后2小时避免摄入乳制品、钙片、铁剂、抗酸药",
        "A",
    ),

    # ---- 地高辛相关 ----
    (
        ["地高辛", "digoxin"],
        ["硝苯地平", "nifedipine", "维拉帕米", "verapamil", "胺碘酮", "amiodarone"],
        "moderate",
        "CCB/胺碘酮降低地高辛清除率",
        "地高辛血药浓度升高→中毒风险（恶心、心律失常、视觉异常）",
        "监测地高辛血药浓度（治疗窗0.8-2.0ng/mL）和中毒体征",
        "B",
    ),

    # ---- ACEI + 钾补充剂/保钾利尿剂 ----
    (
        ["卡托普利", "captopril", "依那普利", "enalapril", "赖诺普利", "lisinopril",
         "氯沙坦", "losartan", "缬沙坦", "valsartan"],
        ["螺内酯", "spironolactone", "氯化钾", "补钾", "potassium"],
        "severe",
        "ACEI/ARB减少醛固酮→钾排出减少+保钾利尿剂/补钾→叠加效应",
        "严重高钾血症→心律失常→心搏骤停",
        "禁止常规联用。心衰特定情况需严密监测血钾",
        "A",
    ),

    # ---- 硝酸酯类 + PDE5抑制剂 ----
    (
        ["硝酸甘油", "nitroglycerin", "单硝酸异山梨酯", "isosorbide mononitrate",
         "硝酸异山梨酯", "isosorbide dinitrate"],
        ["西地那非", "sildenafil", "万艾可", "他达拉非", "tadalafil", "希爱力",
         "伐地那非", "vardenafil"],
        "contraindicated",
        "两者均扩张血管→协同作用→严重低血压",
        "血压骤降→心肌缺血、晕厥、甚至死亡",
        "绝对禁止联用。使用PDE5抑制剂后至少24-48小时内禁用硝酸酯类药物",
        "A",
    ),
]


# ============================================================
# 已知药物禁忌/慎用规则（人群+疾病）
# ============================================================

# 格式: (drug_patterns, condition_pattern, severity, mechanism, recommendation)
POPULATION_RULES = [
    (["华法林", "warfarin"], "孕妇|妊娠|pregnant", "contraindicated",
     "华法林可通过胎盘→胎儿华法林综合征（鼻发育不全、骨骺异常）",
     "妊娠期禁用华法林。备孕期需换用低分子肝素"),
    (["布洛芬", "ibuprofen", "双氯芬酸", "diclofenac", "萘普生", "naproxen",
      "阿司匹林(大剂量)", "吲哚美辛"], "孕妇|妊娠|pregnant", "severe",
     "NSAIDs可致胎儿动脉导管早闭、羊水过少",
     "妊娠晚期（≥30周）禁用"),
    (["阿托伐他汀", "atorvastatin", "辛伐他汀", "simvastatin",
      "瑞舒伐他汀", "rosuvastatin"], "孕妇|妊娠|pregnant", "contraindicated",
     "胆固醇为胎儿发育必需物质",
     "妊娠期和备孕期禁用他汀类。育龄妇女服药期间需避孕"),
    (["卡托普利", "captopril", "依那普利", "enalapril", "氯沙坦", "losartan",
      "缬沙坦", "valsartan"], "孕妇|妊娠|pregnant", "contraindicated",
     "ACEI/ARB可致胎儿肾发育不良、羊水过少、颅骨发育不全",
     "妊娠期禁用RAS抑制剂。备孕期换用其他降压药"),
    (["布洛芬", "ibuprofen", "双氯芬酸", "diclofenac", "阿司匹林(大剂量)"],
     "消化性溃疡|胃溃疡|十二指肠溃疡|peptic ulcer", "severe",
     "NSAIDs抑制COX-1→胃黏膜保护性前列腺素减少→诱发/加重溃疡",
     "活动性溃疡禁用。必须使用时联用PPI"),
    (["二甲双胍", "metformin"], "肾功能不全|肾衰竭|kidney failure", "contraindicated",
     "肾功能不全→二甲双胍清除减少→乳酸酸中毒风险增加",
     "eGFR<30禁用；eGFR 30-45减量使用"),
    (["左氧氟沙星", "levofloxacin", "莫西沙星", "moxifloxacin", "环丙沙星",
      "ciprofloxacin"], "孕妇|妊娠|儿童", "contraindicated",
     "氟喹诺酮类可能影响软骨发育",
     "孕妇和18岁以下禁用"),
    (["地西泮", "diazepam", "安定", "阿普唑仑", "氯硝西泮"],
     "老年|65岁以上|elderly", "moderate",
     "老年人对苯二氮䓬类敏感性增加→跌倒、认知损害风险",
     "老年人避免使用。如必须使用，选择短效制剂并最小剂量"),
]


def _match_drug(drug_name: str, patterns: list[str]) -> bool:
    """检查药物名是否匹配规则中的任意模式"""
    name_lower = drug_name.lower().strip()
    return any(p.lower() in name_lower or name_lower in p.lower() for p in patterns)


# ============================================================
# 规则引擎主接口
# ============================================================

def check_interactions_by_rules(drug_list_str: str) -> str:
    """
    使用硬编码规则检查药物相互作用（不需要 LLM、不需要 KG）

    Args:
        drug_list_str: 逗号分隔的药物名称
    Returns:
        格式化的相互作用检查报告
    """
    drugs = [d.strip() for d in drug_list_str.replace("、", ",").split(",") if d.strip()]

    matched: list[dict[str, Any]] = []

    # 检查药物-药物相互作用
    for i in range(len(drugs)):
        for j in range(i + 1, len(drugs)):
            for rule in CRITICAL_INTERACTIONS:
                patterns_a, patterns_b, sev, mech, effect, rec, ev = rule
                a_matches_b = _match_drug(drugs[i], patterns_a) and _match_drug(drugs[j], patterns_b)
                b_matches_a = _match_drug(drugs[j], patterns_a) and _match_drug(drugs[i], patterns_b)
                if a_matches_b or b_matches_a:
                    matched.append({
                        "drug_a": drugs[i],
                        "drug_b": drugs[j],
                        "severity": sev,
                        "mechanism": mech,
                        "effect": effect,
                        "recommendation": rec,
                        "evidence": ev,
                    })
                    break  # 每对只匹配第一个命中的规则

    # 检查人群/疾病禁忌
    population_matches: list[dict] = []
    # 这里需要 context 参数，暂时只做药物间检查

    # 构建输出
    if not matched:
        return (
            "## 规则引擎检查结果\n\n"
            f"已检查药物：{'、'.join(drugs)}\n\n"
            "✅ 基于内置规则库，未发现已知的严重药物相互作用。\n\n"
            "> ⚠️ 注意：规则引擎仅覆盖最常见的高危相互作用组合，"
            "不排除存在未被收录的相互作用。本结果仅供参考，不可替代专业药师判断。"
        )

    lines = [
        "## 规则引擎 — 药物安全性检查（离线模式）",
        "",
        f"已检查：{'、'.join(drugs)}",
        "",
        "> ⚠️ 当前系统运行在规则引擎降级模式（LLM 不可用）。",
        "> 以下结果基于内置的安全规则库，仅覆盖关键高危相互作用。",
        "",
    ]

    severe_found = [m for m in matched if m["severity"] in ("severe", "contraindicated")]
    if severe_found:
        lines.append(f"### 🚨 发现 {len(severe_found)} 个严重/禁忌相互作用！")
        lines.append("")

    for m in matched:
        sev_icon = {
            "severe": "🔴 严重",
            "contraindicated": "🚫 禁忌",
            "moderate": "🟡 中等",
            "mild": "🟢 轻微",
        }.get(m["severity"], m["severity"])

        lines.append(f"### {m['drug_a']} ↔ {m['drug_b']} [{sev_icon}]")
        lines.append(f"- **机制**: {m['mechanism']}")
        lines.append(f"- **后果**: {m['effect']}")
        lines.append(f"- **建议**: {m['recommendation']}")
        lines.append(f"- **证据等级**: {m['evidence']}")
        lines.append("")

    lines.append("---")
    lines.append("> 💡 规则引擎模式无法提供个性化分析。如需完整的患者特异性评估，请等待系统恢复后重试。")
    lines.append("> 紧急情况请拨打 120 或前往就近医院。")

    return "\n".join(lines)


def check_contraindications_by_rules(
    drug_name: str,
    patient_age: int = 0,
    is_pregnant: str = "否",
    conditions: str = "",
) -> str:
    """
    使用硬编码规则检查特定药物的禁忌症（离线模式）

    Args:
        drug_name: 药物名称
        patient_age: 年龄
        is_pregnant: 是否妊娠（是/否）
        conditions: 现有疾病
    """
    matched: list[dict] = []
    conditions_lower = conditions.lower()

    for rule in POPULATION_RULES:
        patterns, cond_pattern, sev, mech, rec = rule
        if not _match_drug(drug_name, patterns):
            continue

        # 检查人群/疾病是否匹配
        matched_cond = False
        match_reason = ""

        if "孕妇" in cond_pattern and is_pregnant == "是":
            matched_cond = True
            match_reason = "患者处于妊娠期"
        elif "老年" in cond_pattern and patient_age >= 65:
            matched_cond = True
            match_reason = f"患者{patient_age}岁(≥65)"
        elif "儿童" in cond_pattern and 0 < patient_age < 12:
            matched_cond = True
            match_reason = f"患者{patient_age}岁(<12)"
        elif any(c.lower() in conditions_lower for c in cond_pattern.split("|")):
            matched_cond = True
            match_reason = f"患者有「{cond_pattern}」相关情况"

        if matched_cond:
            matched.append({
                "condition": cond_pattern,
                "match_reason": match_reason,
                "severity": sev,
                "mechanism": mech,
                "recommendation": rec,
            })

    if not matched:
        return (
            f"## 规则引擎 — {drug_name} 禁忌症检查\n\n"
            "✅ 基于内置规则库，未发现与当前患者画像直接冲突的禁忌症。\n\n"
            "> 规则引擎仅覆盖有限的关键禁忌症规则，可能存在未覆盖的情况。"
        )

    lines = [
        f"## 规则引擎 — {drug_name} 禁忌症检查（离线模式）",
        "",
    ]
    if patient_age > 0:
        lines.append(f"- 年龄: {patient_age}岁")
    if is_pregnant == "是":
        lines.append(f"- ⚠️ 妊娠期")
    if conditions:
        lines.append(f"- 疾病: {conditions}")
    lines.append("")

    for m in matched:
        sev_label = "🚫 禁忌" if m["severity"] == "contraindicated" else "⚠️ 慎用/避免"
        lines.append(f"### {sev_label}: {m['condition']}")
        lines.append(f"- 匹配原因: {m['match_reason']}")
        lines.append(f"- 机制: {m['mechanism']}")
        lines.append(f"- 建议: {m['recommendation']}")
        lines.append("")

    return "\n".join(lines)
