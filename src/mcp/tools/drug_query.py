"""
用药安全 Graph RAG 工具 — 药品查询、相互作用检查、图谱检索

这些工具通过 Graph RAG 检索器访问药物知识图谱，
为 LLM 提供结构化、可溯源的用药安全上下文。
"""
from __future__ import annotations
import logging

from src.graph_rag.knowledge_graph import knowledge_graph
from src.graph_rag.entity_linker import entity_linker
from src.graph_rag.graph_retriever import graph_retriever

logger = logging.getLogger("drug-query")


# ============================================================
# 工具 1：药品信息查询
# ============================================================

def search_drug_info(drug_name: str) -> str:
    """查询单个药品的详细信息，包括适应症、禁忌症、已知相互作用、食物禁忌等

    Args:
        drug_name: 药物通用名或商品名（如"华法林"、"阿莫西林"、"波立维"）
    """
    if not knowledge_graph.is_loaded:
        return "知识图谱未加载，请联系管理员。"

    # 解析节点
    node_id = knowledge_graph.resolve_node(drug_name)
    if not node_id:
        # 尝试模糊搜索
        results = knowledge_graph.search_nodes(drug_name, node_type="Drug")
        if not results:
            return f"未找到与「{drug_name}」相关的药物信息。请检查药名是否有误，或尝试使用通用名查询。"

        # 多个匹配结果
        lines = [f"找到 {len(results)} 个匹配「{drug_name}」的药物："]
        for r in results[:5]:
            lines.append(f"- {r.get('name', '')} ({r.get('category', '')})")
        return "\n".join(lines)

    # 获取节点详情
    node = knowledge_graph.get_node(node_id)
    if not node:
        return f"无法获取「{drug_name}」的详细信息。"

    # 格式化输出
    lines = [
        f"## {node.get('name', '')}",
        f"- **类别**: {node.get('category', 'N/A')}",
        f"- **处方类型**: {node.get('rx_type', 'N/A')}",
    ]
    if node.get("brand_names"):
        lines.append(f"- **商品名**: {'、'.join(node['brand_names'])}")
    if node.get("atc_code"):
        lines.append(f"- **ATC 编码**: {node['atc_code']}")
    if node.get("description"):
        lines.append(f"- **简介**: {node['description']}")

    # 相互作用
    interactions = knowledge_graph.get_all_interactions(node_id)
    if interactions:
        lines.append("\n### 已知药物相互作用")
        for inter in interactions:
            sev = inter.get("severity", "")
            lines.append(f"- **{inter.get('drug', '')}** [{sev}]")
            if inter.get("effect"):
                lines.append(f"  - 后果: {inter['effect']}")
            if inter.get("recommendation"):
                lines.append(f"  - 建议: {inter['recommendation']}")

    # 食物相互作用
    food_edges = knowledge_graph.get_neighbors(
        node_id,
        edge_types=["FOOD_INTERACTION"],
        max_hops=1,
    )
    if food_edges:
        lines.append("\n### 食物/饮品相互作用")
        for fe in food_edges:
            lines.append(f"- **{fe['target_name']}**")
            if fe.get("mechanism"):
                lines.append(f"  - 机制: {fe['mechanism']}")
            if fe.get("recommendation"):
                lines.append(f"  - 建议: {fe['recommendation']}")

    # 禁忌症
    contraindications = knowledge_graph.get_neighbors(
        node_id,
        edge_types=["CONTRAINDICATED_FOR"],
        max_hops=1,
    )
    if contraindications:
        lines.append("\n### 禁忌症与慎用人群")
        for ci in contraindications:
            lines.append(f"- **{ci['target_name']}** ({ci.get('severity', '')})")
            if ci.get("recommendation"):
                lines.append(f"  - 建议: {ci['recommendation']}")

    return "\n".join(lines)


# ============================================================
# 工具 2：药物相互作用检查
# ============================================================

def check_drug_interactions(drug_list: str) -> str:
    """检查一个或多个药物之间是否存在相互作用，以及药物与食物/保健品之间的冲突

    支持同时检查多个药物，以逗号或顿号分隔。

    Args:
        drug_list: 待检查的药物名称列表，如"华法林, 布洛芬, 鱼油"
    """
    if not knowledge_graph.is_loaded:
        return "知识图谱未加载，请联系管理员。"

    # 解析药物列表
    drug_names = [
        name.strip()
        for name in drug_list.replace("、", ",").split(",")
        if name.strip()
    ]

    if len(drug_names) < 1:
        return "请提供至少一个药物名称进行检查。"

    # 链接到图谱节点
    resolved: list[tuple[str, str]] = []  # (name, node_id)
    unrecognized: list[str] = []

    for name in drug_names:
        node_id = knowledge_graph.resolve_node(name)
        if node_id:
            resolved.append((name, node_id))
        else:
            unrecognized.append(name)

    if not resolved:
        return f"未能识别任何药物名称：{'、'.join(unrecognized)}。请检查拼写或使用通用名。"

    # 使用 Graph Retriever 做全面检索
    query = " ".join(drug_names) + " 相互作用 禁忌"
    ctx = graph_retriever.retrieve(query)

    lines = [ctx.summary]

    if unrecognized:
        lines.append(f"\n> ⚠️ 未能识别：{'、'.join(unrecognized)}，请确认药名。")

    return "\n".join(lines)


# ============================================================
# 工具 3：综合用药安全分析（Graph RAG 全文检索）
# ============================================================

def graph_rag_search(query: str) -> str:
    """
    综合用药安全分析：对用户的自然语言问题做实体链接、子图检索和路径推理，
    返回结构化的用药安全上下文。适用于复杂的用药咨询场景。

    Args:
        query: 用户的自然语言查询，可以包含药物名、症状、食物等
    """
    if not knowledge_graph.is_loaded:
        return "知识图谱未加载，请联系管理员。"

    ctx = graph_retriever.retrieve(query)

    if not ctx.summary.strip() or ctx.summary == "（未在知识图谱中找到相关信息）":
        return (
            "在知识图谱中未找到与您查询直接相关的药物信息。\n\n"
            "建议：\n"
            "1. 尝试使用药物的通用名（而非商品名）进行查询\n"
            "2. 确认药物名称拼写是否正确\n"
            "3. 如果是新型药物，可能尚未收录到知识库中\n"
        )

    return ctx.summary


# ============================================================
# 工具 4：知识图谱统计
# ============================================================

def get_kg_stats() -> str:
    """获取当前知识图谱的统计信息（节点数、边数、覆盖类别等）"""
    if not knowledge_graph.is_loaded:
        return "知识图谱未加载。"

    stats = knowledge_graph.get_stats()
    lines = [
        "## 知识图谱统计",
        f"- 节点总数: {stats['total_nodes']}",
        f"- 边总数: {stats['total_edges']}",
        f"- 别名索引: {stats['aliases_indexed']} 条",
        "\n### 节点类型分布",
    ]
    for ntype, count in sorted(stats["node_types"].items(), key=lambda x: -x[1]):
        lines.append(f"- {ntype}: {count}")

    lines.append("\n### 边类型分布")
    for etype, count in sorted(stats["edge_types"].items(), key=lambda x: -x[1]):
        lines.append(f"- {etype}: {count}")

    return "\n".join(lines)
