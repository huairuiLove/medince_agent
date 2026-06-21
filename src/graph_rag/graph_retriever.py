"""
Graph RAG 检索器 — 实体链接 + 子图检索 + 路径推理 + 上下文格式化

核心检索策略：
  1. 实体链接：从用户输入中抽取药物/食物实体 → 映射到 KG 节点
  2. 子图检索：以命中节点为中心，N 跳遍历邻居
  3. 路径推理：当涉及多个药物时，查找相互作用路径
  4. 结果格式化：将结构化图数据转为 LLM 可理解的上下文文本
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Any

from src.graph_rag.entity_linker import entity_linker, LinkingResult
from src.graph_rag.knowledge_graph import knowledge_graph
from src.graph_rag.schema import EdgeType, SubgraphResult, PathResult

logger = logging.getLogger("graph-retriever")


@dataclass
class RetrievalContext:
    """一次 Graph RAG 检索的完整上下文"""
    query: str                                          # 原始查询
    linked_drugs: list[dict[str, Any]] = field(default_factory=list)
    linked_others: list[dict[str, Any]] = field(default_factory=list)
    interactions: list[dict[str, Any]] = field(default_factory=list)
    contraindications: list[dict[str, Any]] = field(default_factory=list)
    food_interactions: list[dict[str, Any]] = field(default_factory=list)
    paths_between_drugs: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""                                   # 格式化的摘要文本
    citations: list[dict[str, Any]] = field(default_factory=list)  # 🆕 结构化引用


class GraphRetriever:
    """Graph RAG 检索器"""

    def __init__(self) -> None:
        pass

    # ---------------------------------------------------------------
    # 主入口：检索 + 格式化
    # ---------------------------------------------------------------

    def retrieve(self, query: str) -> RetrievalContext:
        """
        对用户查询做完整的 Graph RAG 检索：
          1. 实体链接
          2. 多角度子图检索
          3. 格式化上下文

        Returns:
            RetrievalContext，其中 .summary 可直接注入 LLM 上下文
        """
        ctx = RetrievalContext(query=query)

        # 1. 实体链接
        linking = entity_linker.link(query)

        # 分类实体：Drug vs 其他
        for ent in linking.entities:
            node = knowledge_graph.get_node(ent.node_id)
            if not node:
                continue
            info = {
                "node_id": ent.node_id,
                "name": node.get("name", ""),
                "type": node.get("type", ""),
                "category": node.get("category", ""),
                "brand_names": node.get("brand_names", []),
                "description": node.get("description", ""),
                "match_method": ent.match_method,
                "confidence": ent.confidence,
            }
            if node.get("type") == "Drug":
                ctx.linked_drugs.append(info)
            else:
                ctx.linked_others.append(info)

        logger.info(
            "Retrieved: %d drugs, %d others from query",
            len(ctx.linked_drugs), len(ctx.linked_others),
        )

        # 2. 对每个匹配到的药物，获取相互作用和禁忌症
        for drug in ctx.linked_drugs:
            nid = drug["node_id"]

            # 药物相互作用
            interactions = knowledge_graph.get_all_interactions(nid)
            for inter in interactions:
                ctx.interactions.append({
                    "drug_a": drug["name"],
                    "drug_b": inter.get("drug", ""),
                    "severity": inter.get("severity", ""),
                    "mechanism": inter.get("mechanism", ""),
                    "effect": inter.get("effect", ""),
                    "recommendation": inter.get("recommendation", ""),
                    "evidence_level": inter.get("evidence_level", ""),
                })

            # 禁忌症和食物相互作用
            neighbors = knowledge_graph.get_neighbors(
                nid,
                edge_types=[
                    EdgeType.CONTRAINDICATED_FOR.value,
                    EdgeType.FOOD_INTERACTION.value,
                ],
                max_hops=1,
            )
            for nbr in neighbors:
                entry = {
                    "drug": drug["name"],
                    "target": nbr["target_name"],
                    "target_type": nbr["target_type"],
                    "edge_type": nbr["edge_type"],
                    "severity": nbr.get("severity", ""),
                    "mechanism": nbr.get("mechanism", ""),
                    "effect": nbr.get("effect", ""),
                    "recommendation": nbr.get("recommendation", ""),
                    "evidence_level": nbr.get("evidence_level", ""),
                }
                if nbr["edge_type"] == EdgeType.CONTRAINDICATED_FOR.value:
                    ctx.contraindications.append(entry)
                elif nbr["edge_type"] == EdgeType.FOOD_INTERACTION.value:
                    ctx.food_interactions.append(entry)

        # 3. 如果有多个药物，查找它们之间的直接路径
        drug_ids = [d["node_id"] for d in ctx.linked_drugs]
        if len(drug_ids) >= 2:
            for i in range(len(drug_ids)):
                for j in range(i + 1, len(drug_ids)):
                    path_result = knowledge_graph.find_paths(
                        drug_ids[i], drug_ids[j], max_length=3
                    )
                    if path_result.paths:
                        for path in path_result.paths:
                            # 将路径节点 ID 转为名称
                            path_names = []
                            for nid in path:
                                node = knowledge_graph.get_node(nid)
                                path_names.append(node["name"] if node else nid)

                            ctx.paths_between_drugs.append({
                                "drug_a": ctx.linked_drugs[i]["name"],
                                "drug_b": ctx.linked_drugs[j]["name"],
                                "path": path_names,
                                "length": len(path_names),
                            })

        # 4. 生成结构化引用
        ctx.citations = self._generate_citations(ctx)

        # 5. 格式化摘要（包含引用标记）
        ctx.summary = self._format_context(ctx)
        return ctx

    # ---------------------------------------------------------------
    # 上下文格式化
    # ---------------------------------------------------------------

    def _format_context(self, ctx: RetrievalContext) -> str:
        """将检索结果格式化为结构化文本，供 LLM 上下文使用"""
        parts: list[str] = []

        # 匹配到的药物
        if ctx.linked_drugs:
            parts.append("## 识别到的药物")
            for d in ctx.linked_drugs:
                brands = f"（商品名：{'、'.join(d['brand_names'])}）" if d["brand_names"] else ""
                desc = f" — {d['description']}" if d.get("description") else ""
                parts.append(f"- **{d['name']}**{brands} [{d.get('category', '')}]{desc}")

        # 药物相互作用
        if ctx.interactions:
            # 去重
            seen = set()
            unique_inters = []
            for inter in ctx.interactions:
                key = tuple(sorted([inter["drug_a"], inter["drug_b"]]))
                if key not in seen:
                    seen.add(key)
                    unique_inters.append(inter)

            parts.append("\n## ⚠️ 药物相互作用")
            for inter in unique_inters:
                sev_icon = {
                    "severe": "🔴 严重",
                    "contraindicated": "🚫 禁忌",
                    "moderate": "🟡 中等",
                    "mild": "🟢 轻微",
                }.get(inter["severity"], inter["severity"])

                parts.append(
                    f"\n### {inter['drug_a']} ↔ {inter['drug_b']} [{sev_icon}]\n"
                    f"- **机制**: {inter.get('mechanism', '未知')}\n"
                    f"- **后果**: {inter.get('effect', '未知')}\n"
                    f"- **建议**: {inter.get('recommendation', '请咨询医生')}\n"
                    f"- **证据等级**: {inter.get('evidence_level', 'N/A')}"
                )

        # 禁忌症
        if ctx.contraindications:
            parts.append("\n## 🚫 禁忌症与慎用人群")
            for c in ctx.contraindications:
                sev = "🚫 禁忌" if c["severity"] == "contraindicated" else "⚠️ 慎用"
                parts.append(f"- **{c['drug']}** → {c['target']} [{sev}]")
                if c.get("recommendation"):
                    parts.append(f"  - 建议: {c['recommendation']}")

        # 食物相互作用
        if ctx.food_interactions:
            parts.append("\n## 🍽️ 食物与饮品相互作用")
            for f in ctx.food_interactions:
                parts.append(f"- **{f['drug']}** ↔ {f['target']}")
                if f.get("mechanism"):
                    parts.append(f"  - 机制: {f['mechanism']}")
                if f.get("recommendation"):
                    parts.append(f"  - 建议: {f['recommendation']}")

        # 药物间路径
        if ctx.paths_between_drugs:
            parts.append("\n## 🔗 药物间关系路径")
            for p in ctx.paths_between_drugs:
                path_str = " → ".join(p["path"])
                parts.append(f"- {p['drug_a']} → {p['drug_b']}: `{path_str}`")

        # 追加引用索引
        if ctx.citations:
            parts.append("\n## 📖 引用来源")
            for i, cite in enumerate(ctx.citations, 1):
                level_icon = {"A": "🟢", "B": "🟡", "C": "🟠", "D": "🔴"}.get(
                    cite.get("evidence_level", ""), "⚪"
                )
                parts.append(
                    f"[{i}] {level_icon} {cite.get('citation_text', '')} "
                    f"(置信度: {cite.get('confidence', 0):.0%})"
                )

        if len(parts) == 0:
            return "（未在知识图谱中找到相关信息）"

        return "\n".join(parts)

    def _generate_citations(self, ctx: RetrievalContext) -> list[dict[str, Any]]:
        """从检索结果生成结构化引用列表"""
        citations: list[dict] = []
        cid = 0

        for inter in ctx.interactions:
            cid += 1
            sev = inter.get("severity", "")
            citations.append({
                "id": f"cite_{cid}",
                "source_type": "kg_edge",
                "drug_a": inter.get("drug_a", ""),
                "drug_b": inter.get("drug_b", ""),
                "severity": sev,
                "mechanism": inter.get("mechanism", ""),
                "evidence_level": inter.get("evidence_level", ""),
                "confidence": 0.95 if inter.get("evidence_level") in ("A", "B") else 0.80,
                "citation_text": f"{inter.get('drug_a','')} ↔ {inter.get('drug_b','')} — {inter.get('effect','')[:60]}",
            })

        for ci in ctx.contraindications:
            cid += 1
            citations.append({
                "id": f"cite_{cid}",
                "source_type": "kg_contraindication",
                "drug": ci.get("drug", ""),
                "target": ci.get("target", ""),
                "severity": ci.get("severity", ""),
                "recommendation": ci.get("recommendation", ""),
                "evidence_level": "B",
                "confidence": 0.90,
                "citation_text": f"{ci.get('drug','')} 禁忌人群: {ci.get('target','')}",
            })

        for fi in ctx.food_interactions:
            cid += 1
            citations.append({
                "id": f"cite_{cid}",
                "source_type": "kg_food",
                "drug": fi.get("drug", ""),
                "food": fi.get("target", ""),
                "recommendation": fi.get("recommendation", ""),
                "evidence_level": fi.get("evidence_level", "C"),
                "confidence": 0.85,
                "citation_text": f"{fi.get('drug','')} ↔ {fi.get('target','')} (食物相互作用)",
            })

        return citations


# ============================================================
# 模块级单例
# ============================================================

graph_retriever = GraphRetriever()
