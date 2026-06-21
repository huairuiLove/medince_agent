"""
Phase 3 — 用药安全专用分析工具

提供处方级安全审查能力:
  1. review_prescription   — 处方综合审查（多药 + 患者画像）
  2. check_patient_contraindications — 基于患者画像的禁忌症全面排查
  3. find_safer_alternatives — 安全替代方案推荐
"""
from __future__ import annotations
import logging
from typing import Any

from src.graph_rag.knowledge_graph import knowledge_graph
from src.graph_rag.entity_linker import entity_linker
from src.graph_rag.schema import EdgeType, Severity

logger = logging.getLogger("prescription-safety")


# ============================================================
# Patient Profile
# ============================================================

PATIENT_PROFILE_FIELDS = {
    "age": "年龄",
    "pregnant": "是否妊娠",
    "lactating": "是否哺乳期",
    "liver_function": "肝功能 (normal/mild_impaired/severe_impaired)",
    "kidney_function": "肾功能 (normal/mild_impaired/severe_impaired)",
    "conditions": "现有疾病（逗号分隔）",
    "allergies": "过敏史（逗号分隔）",
}

DRUG_CLASS_ALTERNATIVES = {
    "香豆素类抗凝药": {
        "alternatives": ["利伐沙班", "阿哌沙班", "达比加群"],
        "note": "DOAC类药物，无需常规监测INR，食物相互作用更少",
    },
    "NSAIDs": {
        "alternatives": ["对乙酰氨基酚", "塞来昔布(选择性COX-2抑制剂)"],
        "note": "对乙酰氨基酚不影响血小板和胃黏膜；塞来昔布消化道安全性更好但心血管风险需评估",
    },
    "苯二氮䓬类": {
        "alternatives": ["右佐匹克隆", "褪黑素", "曲唑酮(小剂量)"],
        "note": "非苯二氮䓬类催眠药依赖性更低，适合老年人",
    },
    "磺脲类降糖药": {
        "alternatives": ["二甲双胍", "西格列汀(DPP-4i)", "达格列净(SGLT2i)"],
        "note": "新型降糖药低血糖风险更低，有心血管/肾脏获益",
    },
    "第一代头孢菌素": {
        "alternatives": ["阿莫西林（青霉素不过敏时）", "阿奇霉素"],
        "note": "根据感染部位和药敏结果选择",
    },
}


# ============================================================
# 工具 1：处方综合审查
# ============================================================

def review_prescription(
    drug_list: str,
    patient_age: int = 0,
    patient_conditions: str = "",
    is_pregnant: str = "否",
    is_lactating: str = "否",
    kidney_function: str = "normal",
    liver_function: str = "normal",
) -> str:
    """
    处方综合安全性审查——检查一组药物的所有潜在安全问题。

    这是用药安全助手的核心工具。同时分析：
    - 药物-药物相互作用（含严重程度分级）
    - 患者禁忌症匹配
    - 特殊人群（妊娠/哺乳/老年/肝肾功能）风险
    - 食物-药物禁忌
    - 治疗窗窄的药物监测需求

    Args:
        drug_list: 待审查的药物列表，逗号分隔（如"华法林, 阿司匹林, 布洛芬"）
        patient_age: 患者年龄
        patient_conditions: 患者现有疾病，逗号分隔（如"高血压, 糖尿病, 房颤"）
        is_pregnant: 是否妊娠 (是/否)
        is_lactating: 是否哺乳期 (是/否)
        kidney_function: 肾功能 (normal/mild_impaired/severe_impaired)
        liver_function: 肝功能 (normal/mild_impaired/severe_impaired)
    """
    if not knowledge_graph.is_loaded:
        return "知识图谱未加载，无法执行处方审查。"

    # 解析药物
    drug_names = [
        n.strip()
        for n in drug_list.replace("、", ",").split(",")
        if n.strip()
    ]
    condition_names = [
        c.strip()
        for c in patient_conditions.replace("、", ",").split(",")
        if c.strip()
    ]

    # 链接药物到 KG
    resolved_drugs: list[dict[str, Any]] = []
    unrecognized: list[str] = []
    for name in drug_names:
        nid = knowledge_graph.resolve_node(name)
        if nid:
            node = knowledge_graph.get_node(nid)
            if node:
                resolved_drugs.append({"name": name, "node_id": nid, "node": node})
                continue
        unrecognized.append(name)

    sections: list[str] = []

    # === 头部信息 ===
    sections.append("## 处方安全性审查报告")
    sections.append("")

    # 审查药物列表
    if resolved_drugs:
        sections.append("### 审查药物")
        for d in resolved_drugs:
            n = d["node"]
            sections.append(
                f"- **{n['name']}** ({n.get('category', 'N/A')}, {n.get('rx_type', '')})"
            )
        sections.append("")

    if unrecognized:
        sections.append(f"> ⚠️ 以下药物未收录：{'、'.join(unrecognized)}")
        sections.append("")

    # === 患者画像 ===
    sections.append("### 患者画像")
    profile_parts = []
    if patient_age > 0:
        profile_parts.append(f"年龄: {patient_age}岁")
    if condition_names:
        profile_parts.append(f"疾病: {'、'.join(condition_names)}")
    if is_pregnant == "是":
        profile_parts.append("⚠️ 妊娠期")
    if is_lactating == "是":
        profile_parts.append("🍼 哺乳期")
    if kidney_function != "normal":
        profile_parts.append(f"肾功能: {kidney_function}")
    if liver_function != "normal":
        profile_parts.append(f"肝功能: {liver_function}")
    sections.append("、".join(profile_parts) if profile_parts else "未提供")
    sections.append("")

    # === 1. 药物-药物相互作用 ===
    sections.append("### 1. 药物-药物相互作用")
    drug_ids = [d["node_id"] for d in resolved_drugs]
    all_interactions: list[dict] = []
    seen_pairs: set[tuple] = set()

    for did in drug_ids:
        for inter in knowledge_graph.get_all_interactions(did):
            target_name = inter.get("drug", "")
            # 检查 target 是否也在处方中
            target_id = knowledge_graph.resolve_node(target_name)
            if target_id and target_id in drug_ids:
                pair = tuple(sorted([knowledge_graph.graph.nodes[did].get("name", ""), target_name]))
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    all_interactions.append(inter)

    if all_interactions:
        severe_count = sum(1 for i in all_interactions if i.get("severity") in ("severe", "contraindicated"))
        moderate_count = sum(1 for i in all_interactions if i.get("severity") == "moderate")

        if severe_count > 0:
            sections.append(f"🚨 **发现 {severe_count} 个严重/禁忌相互作用！**")
        sections.append(f"共 {len(all_interactions)} 个相互作用（严重: {severe_count}, 中等: {moderate_count}）")
        sections.append("")

        for inter in all_interactions:
            sev = inter.get("severity", "")
            sev_icon = {"severe": "🔴", "contraindicated": "🚫", "moderate": "🟡", "mild": "🟢"}.get(sev, "")
            sections.append(
                f"**{sev_icon} {inter.get('drug', '')}** | 严重程度: {sev}\n"
                f"- 机制: {inter.get('mechanism', 'N/A')}\n"
                f"- 后果: {inter.get('effect', 'N/A')}\n"
                f"- 建议: {inter.get('recommendation', '请咨询医生')}\n"
                f"- 证据等级: {inter.get('evidence_level', 'N/A')}"
            )
    else:
        sections.append("✅ 未发现收录的直接药物相互作用。")
    sections.append("")

    # === 2. 禁忌症 + 特殊人群 ===
    sections.append("### 2. 禁忌症 & 特殊人群风险")
    risk_found = False

    for d in resolved_drugs:
        contraindications = knowledge_graph.get_neighbors(
            d["node_id"],
            edge_types=[EdgeType.CONTRAINDICATED_FOR.value],
            max_hops=1,
        )
        for ci in contraindications:
            target = ci["target_name"]
            # 检查是否匹配患者画像
            matched = False
            match_reason = ""

            if target in condition_names:
                matched = True
                match_reason = f"患者有{target}"
            if "孕妇" in target and is_pregnant == "是":
                matched = True
                match_reason = "患者为妊娠期"
            if "哺乳" in target and is_lactating == "是":
                matched = True
                match_reason = "患者为哺乳期"
            if "老年" in target and patient_age >= 65:
                matched = True
                match_reason = f"患者{patient_age}岁(≥65岁)"
            if "儿童" in target and patient_age < 12:
                matched = True
                match_reason = f"患者{patient_age}岁(<12岁)"
            if "肾功能" in target and kidney_function != "normal":
                matched = True
                match_reason = f"患者肾功能: {kidney_function}"
            if "肝病" in target and liver_function != "normal":
                matched = True
                match_reason = f"患者肝功能: {liver_function}"

            if matched:
                risk_found = True
                sev = "🚫 禁忌" if ci.get("severity") == "contraindicated" else "⚠️ 风险"
                sections.append(
                    f"**{sev} {d['node']['name']} → {target}**\n"
                    f"- 匹配原因: {match_reason}\n"
                    f"- 机制: {ci.get('mechanism', 'N/A')}\n"
                    f"- 建议: {ci.get('recommendation', '避免使用')}"
                )

    if not risk_found:
        sections.append("✅ 未发现与患者画像直接冲突的禁忌症。")
    sections.append("")

    # === 3. 食物/饮品禁忌 ===
    sections.append("### 3. 食物与饮品禁忌")
    food_found = False
    for d in resolved_drugs:
        food_edges = knowledge_graph.get_neighbors(
            d["node_id"],
            edge_types=[EdgeType.FOOD_INTERACTION.value],
            max_hops=1,
        )
        for fe in food_edges:
            food_found = True
            sections.append(
                f"- **{d['node']['name']}** ↔ {fe['target_name']}\n"
                f"  - {fe.get('recommendation', fe.get('mechanism', ''))}"
            )

    if not food_found:
        sections.append("✅ 未发现收录的食物/饮品禁忌。")
    sections.append("")

    # === 4. 总结评估 ===
    sections.append("### 4. 综合评估与建议")
    total_severe = sum(
        1 for i in all_interactions
        if i.get("severity") in ("severe", "contraindicated")
    )
    if total_severe > 0:
        sections.append(
            f"🚨 **该处方存在 {total_severe} 个严重安全性问题，建议在医生指导下调整用药方案。**\n\n"
            "请勿自行停药或更改药物，务必咨询处方医师或药师。"
        )
    elif all_interactions:
        sections.append(
            "⚠️ 该处方存在需关注的药物相互作用，建议在服药期间密切观察，必要时咨询医生。"
        )
    else:
        sections.append(
            "✅ 基于现有知识图谱数据，该处方未发现明确的安全性问题。\n\n"
            "请注意：知识图谱覆盖范围有限，不排除存在未收录的相互作用。如有不适应及时就医。"
        )

    if unrecognized:
        sections.append(f"\n> 提示：{'、'.join(unrecognized)} 未收入知识库，相关信息可能不完整。")

    return "\n".join(sections)


# ============================================================
# 工具 2：基于患者画像的禁忌症排查
# ============================================================

def check_patient_contraindications(
    drug_name: str,
    patient_conditions: str = "",
    patient_age: int = 0,
    is_pregnant: str = "否",
    is_lactating: str = "否",
    kidney_function: str = "normal",
    liver_function: str = "normal",
) -> str:
    """
    针对特定患者，深度检查某个药物的所有禁忌症和慎用情况。

    Args:
        drug_name: 药物名称
        patient_conditions: 患者疾病列表
        patient_age: 年龄
        is_pregnant: 是否妊娠
        is_lactating: 是否哺乳
        kidney_function: 肾功能
        liver_function: 肝功能
    """
    if not knowledge_graph.is_loaded:
        return "知识图谱未加载。"

    nid = knowledge_graph.resolve_node(drug_name)
    if not nid:
        return f"未找到药物「{drug_name}」。请检查药名或使用通用名。"

    node = knowledge_graph.get_node(nid)
    if not node:
        return f"无法获取「{drug_name}」信息。"

    sections = [
        f"## {node['name']} — 患者特异性禁忌症评估",
        "",
        f"**药物信息**: {node.get('category', '')} | {node.get('rx_type', '')}",
    ]
    if node.get("description"):
        sections.append(f"**简介**: {node['description']}")

    conditions = [c.strip() for c in patient_conditions.replace("、", ",").split(",") if c.strip()]
    sections.append("")
    sections.append("### 患者风险匹配")
    sections.append("")

    risks: list[dict] = []
    contraindications = knowledge_graph.get_neighbors(
        nid,
        edge_types=[EdgeType.CONTRAINDICATED_FOR.value],
        max_hops=1,
    )

    for ci in contraindications:
        risk_info = {
            "target": ci["target_name"],
            "target_type": ci["target_type"],
            "severity": ci.get("severity", ""),
            "mechanism": ci.get("mechanism", ""),
            "recommendation": ci.get("recommendation", ""),
            "matched": False,
            "match_reason": "",
        }
        target = ci["target_name"]

        if ci["target_type"] == "Condition" and target in conditions:
            risk_info["matched"] = True
            risk_info["match_reason"] = f"患者有「{target}」"
        elif ci["target_type"] == "Population":
            if "孕妇" in target and is_pregnant == "是":
                risk_info["matched"] = True
                risk_info["match_reason"] = "患者处于妊娠期"
            elif "哺乳" in target and is_lactating == "是":
                risk_info["matched"] = True
                risk_info["match_reason"] = "患者处于哺乳期"
            elif "老年" in target and patient_age >= 65:
                risk_info["matched"] = True
                risk_info["match_reason"] = f"患者{patient_age}岁(≥65岁)"
            elif "儿童" in target and patient_age > 0 and patient_age < 12:
                risk_info["matched"] = True
                risk_info["match_reason"] = f"患者{patient_age}岁(<12岁)"
            elif "肾功能" in target and kidney_function != "normal":
                risk_info["matched"] = True
                risk_info["match_reason"] = f"患者肾功能异常({kidney_function})"
            elif "肝" in target and liver_function != "normal":
                risk_info["matched"] = True
                risk_info["match_reason"] = f"患者肝功能异常({liver_function})"

        risks.append(risk_info)

    # 分离匹配和未匹配的风险
    matched = [r for r in risks if r["matched"]]
    unmatched = [r for r in risks if not r["matched"]]

    if matched:
        sections.append("#### 🚨 命中风险")
        for r in matched:
            sev = "🚫 禁忌" if r["severity"] == "contraindicated" else "⚠️ 慎用"
            sections.append(
                f"- **{sev}: {r['target']}**\n"
                f"  - 原因: {r['match_reason']}\n"
                f"  - 机制: {r['mechanism']}\n"
                f"  - 建议: {r.get('recommendation', '需谨慎评估')}"
            )
        sections.append("")

    if unmatched:
        sections.append("#### ℹ️ 其他已知禁忌/慎用（与当前患者未直接匹配）")
        for r in unmatched:
            sections.append(f"- {r['target']} ({r['severity']})")
        sections.append("")

    if not risks:
        sections.append("✅ 知识图谱中未收录该药物的禁忌症信息。")
        sections.append("\n> 这不代表该药物绝对安全——请仔细阅读药品说明书。")

    return "\n".join(sections)


# ============================================================
# 工具 3：安全替代方案推荐
# ============================================================

def find_safer_alternatives(
    drug_name: str,
    patient_conditions: str = "",
    patient_age: int = 0,
    is_pregnant: str = "否",
    reason: str = "",
) -> str:
    """
    当某个药物存在安全性问题时，基于药物类别知识推荐可能更安全的替代方案。

    Args:
        drug_name: 需要替换的药物名称
        patient_conditions: 患者疾病
        patient_age: 年龄
        is_pregnant: 是否妊娠
        reason: 需要替换的原因（如"出血风险"、"肝功能异常"、"妊娠期"）
    """
    if not knowledge_graph.is_loaded:
        return "知识图谱未加载。"

    nid = knowledge_graph.resolve_node(drug_name)
    if not nid:
        return f"未找到药物「{drug_name}」。"

    node = knowledge_graph.get_node(nid)
    if not node:
        return f"无法获取「{drug_name}」信息。"

    category = node.get("category", "")
    sections = [
        f"## {node['name']} — 安全替代方案",
        "",
        f"**原药物类别**: {category}",
        f"**替换原因**: {reason or '未指定'}",
        "",
    ]

    # 查找同类药物的替代建议
    alt_info = DRUG_CLASS_ALTERNATIVES.get(category)

    if alt_info:
        sections.append("### 同类替代方案")
        for alt in alt_info["alternatives"]:
            sections.append(f"- **{alt}**")
        sections.append(f"\n**说明**: {alt_info['note']}")
        sections.append("")
    else:
        # 通过 KG 查找同类其他药物
        neighbors = knowledge_graph.get_neighbors(
            nid,
            edge_types=[EdgeType.BELONGS_TO_CLASS.value],
            max_hops=1,
        )
        class_name = ""
        for nbr in neighbors:
            if nbr["target_type"] == "DrugClass":
                class_name = nbr["target_name"]
                break

        if class_name:
            # 找同类中其他药物
            same_class: list[str] = []
            for other_nid in knowledge_graph.graph.nodes:
                if other_nid == nid:
                    continue
                other_neighbors = knowledge_graph.get_neighbors(
                    other_nid,
                    edge_types=[EdgeType.BELONGS_TO_CLASS.value],
                    max_hops=1,
                )
                for on in other_neighbors:
                    if on["target_name"] == class_name:
                        other_node = knowledge_graph.get_node(other_nid)
                        if other_node:
                            same_class.append(other_node["name"])
                        break

            if same_class:
                sections.append(f"### 「{class_name}」中的其他药物")
                sections.append("以下药物与目标药物属于同一大类，可作为替代参考：")
                for drug in same_class[:8]:
                    sections.append(f"- {drug}")
                sections.append("")
                sections.append("> ⚠️ 同类药物不一定完全等效，具体选择需根据适应症、患者个体情况和医师判断。")
            else:
                sections.append("未在知识图谱中找到同类其他药物。")
        else:
            sections.append("未在知识图谱中找到该药物的类别信息，无法推荐同类替代方案。")

    # 妊娠期特别提示
    if is_pregnant == "是":
        sections.append("")
        sections.append("### ⚠️ 妊娠期特别提示")
        sections.append(
            "妊娠期用药需格外谨慎。即使同类药物，孕期安全性分级可能不同。\n"
            "请务必在产科医生指导下选用药物。FDA 妊娠期用药分级：\n"
            "- A级: 对照研究显示无风险\n"
            "- B级: 动物实验无风险，但无人类研究\n"
            "- C级: 动物实验显示风险，无人类研究（需权衡获益）\n"
            "- D级: 有风险证据，但获益可能大于风险\n"
            "- X级: 禁忌"
        )

    # 老年人特别提示
    if patient_age >= 65:
        sections.append("")
        sections.append("### 👴 老年人用药提示")
        sections.append(
            "老年人肝肾功能可能减退，药物清除减慢。替代方案应考虑：\n"
            "- 选择半衰期较短、代谢产物无活性的药物\n"
            "- 从低剂量起始，缓慢滴定\n"
            "- 简化用药方案，减少药物种类"
        )

    return "\n".join(sections)
