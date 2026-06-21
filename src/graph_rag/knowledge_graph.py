"""
知识图谱引擎 — 基于 NetworkX 的内存图

职责：
  1. 从 JSON 种子数据构建 MultiDiGraph
  2. 提供节点/边查询
  3. N 跳邻居遍历
  4. 最短路径查找
"""
from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Any
from collections import defaultdict

import networkx as nx

from src.graph_rag.schema import (
    NodeType,
    EdgeType,
    Severity,
    SubgraphResult,
    PathResult,
)

logger = logging.getLogger("knowledge-graph")

# 默认种子数据路径
DEFAULT_KG_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "knowledge" / "drug_kg.json"


class KnowledgeGraph:
    """药物安全知识图谱"""

    def __init__(self) -> None:
        self.graph = nx.MultiDiGraph()
        self._node_index: dict[str, str] = {}       # 别名 → node_id
        self._node_attrs: dict[str, dict] = {}      # node_id → 属性
        self._loaded = False

    # ---------------------------------------------------------------
    # 构建
    # ---------------------------------------------------------------

    def load_from_json(self, path: str | Path | None = None) -> int:
        """从 JSON 文件加载图谱数据，返回加载的节点数"""
        if path is None:
            path = DEFAULT_KG_PATH

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self._build(data)
        self._loaded = True

        node_count = self.graph.number_of_nodes()
        edge_count = self.graph.number_of_edges()
        alias_count = len(self._node_index)
        logger.info(
            "KnowledgeGraph loaded: %d nodes, %d edges, %d aliases",
            node_count, edge_count, alias_count
        )
        return node_count

    def _build(self, data: dict[str, Any]) -> None:
        """从结构化数据构建 NetworkX 图"""
        # 1. 添加节点
        for node in data.get("nodes", []):
            node_id = node["id"]
            self.graph.add_node(
                node_id,
                type=node.get("type", "Unknown"),
                name=node.get("name", node_id),
                **{k: v for k, v in node.items() if k not in ("id", "type", "name")},
            )
            self._node_attrs[node_id] = dict(node)

            # 索引：名称 → node_id
            name = node.get("name", "")
            if name:
                self._node_index[name.lower()] = node_id
            # 索引：别名（如商品名）
            for alias in node.get("brand_names", []):
                self._node_index[alias.lower()] = node_id
            # 索引：node_id 自身
            self._node_index[node_id.lower()] = node_id

        # 2. 添加边
        for edge in data.get("edges", []):
            src = edge["source"]
            tgt = edge["target"]
            etype = edge.get("type", "RELATED_TO")

            # 跳过不存在的节点
            if src not in self.graph or tgt not in self.graph:
                logger.warning("Skipping edge %s→%s: node not found", src, tgt)
                continue

            self.graph.add_edge(
                src, tgt,
                type=etype,
                severity=edge.get("severity", ""),
                mechanism=edge.get("mechanism", ""),
                effect=edge.get("effect", ""),
                recommendation=edge.get("recommendation", ""),
                evidence_level=edge.get("evidence_level", ""),
            )

    # ---------------------------------------------------------------
    # 查询
    # ---------------------------------------------------------------

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def node_count(self) -> int:
        return self.graph.number_of_nodes()

    def edge_count(self) -> int:
        return self.graph.number_of_edges()

    def resolve_node(self, name: str) -> str | None:
        """通过名称（通用名/商品名/ID）解析到规范 node_id"""
        return self._node_index.get(name.lower())

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        """获取节点完整属性"""
        if node_id not in self.graph:
            return None
        attrs = dict(self.graph.nodes[node_id])
        attrs["id"] = node_id
        return attrs

    def get_neighbors(
        self, node_id: str, edge_types: list[str] | None = None, max_hops: int = 1
    ) -> list[dict[str, Any]]:
        """获取节点的 N 跳邻居及边信息"""
        if node_id not in self.graph:
            return []

        results: list[dict] = []
        visited: set[str] = {node_id}
        frontier = {node_id}

        for hop in range(max_hops):
            next_frontier: set[str] = set()
            for current in frontier:
                for neighbor in self.graph.neighbors(current):
                    if neighbor in visited:
                        continue
                    edges = self.graph.get_edge_data(current, neighbor)
                    for key, edge_data in (edges or {}).items():
                        if edge_types and edge_data.get("type") not in edge_types:
                            continue
                        results.append({
                            "source": current,
                            "source_name": self.graph.nodes[current].get("name", current),
                            "target": neighbor,
                            "target_name": self.graph.nodes[neighbor].get("name", neighbor),
                            "target_type": self.graph.nodes[neighbor].get("type", ""),
                            "edge_type": edge_data.get("type", ""),
                            "severity": edge_data.get("severity", ""),
                            "mechanism": edge_data.get("mechanism", ""),
                            "effect": edge_data.get("effect", ""),
                            "recommendation": edge_data.get("recommendation", ""),
                            "evidence_level": edge_data.get("evidence_level", ""),
                            "hop": hop + 1,
                        })
                    next_frontier.add(neighbor)
                    visited.add(neighbor)
            frontier = next_frontier

        return results

    def get_subgraph(
        self, node_ids: list[str], hops: int = 2
    ) -> SubgraphResult:
        """获取以指定节点为中心的子图"""
        all_nodes: set[str] = set(node_ids)
        all_edges: list[dict] = []

        for nid in node_ids:
            if nid not in self.graph:
                continue
            neighbors = self.get_neighbors(nid, max_hops=hops)
            for nbr in neighbors:
                all_nodes.add(nbr["source"])
                all_nodes.add(nbr["target"])
                all_edges.append(nbr)

        nodes_data = []
        for nid in all_nodes:
            node = self.get_node(nid)
            if node:
                nodes_data.append(node)

        return SubgraphResult(
            center_node=node_ids[0] if node_ids else "",
            center_type=self.graph.nodes[node_ids[0]].get("type", "") if node_ids else "",
            nodes=nodes_data,
            edges=all_edges,
            hop_count=hops,
        )

    def find_paths(
        self, source_id: str, target_id: str, max_length: int = 4
    ) -> PathResult:
        """查找两个节点之间的所有短路径（用于相互作用追踪）"""
        paths: list[list[str]] = []
        try:
            raw_paths = list(
                nx.all_simple_paths(self.graph, source_id, target_id, cutoff=max_length)
            )
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            raw_paths = []

        for p in raw_paths:
            paths.append(p)

        shortest = min((len(p) for p in paths), default=0)

        return PathResult(
            source=source_id,
            target=target_id,
            paths=paths,
            path_count=len(paths),
            shortest_length=shortest,
        )

    def get_all_interactions(self, node_id: str) -> list[dict[str, Any]]:
        """获取某个药物节点的所有相互作用（出边+入边）"""
        interactions: list[dict] = []

        # 出边
        for _, neighbor, data in self.graph.out_edges(node_id, data=True):
            if data.get("type") == EdgeType.INTERACTS_WITH.value:
                interactions.append({
                    "drug": self.graph.nodes[neighbor].get("name", neighbor),
                    "direction": "out",
                    **data,
                })

        # 入边
        for predecessor, _, data in self.graph.in_edges(node_id, data=True):
            if data.get("type") == EdgeType.INTERACTS_WITH.value:
                interactions.append({
                    "drug": self.graph.nodes[predecessor].get("name", predecessor),
                    "direction": "in",
                    **data,
                })

        return interactions

    def search_nodes(self, keyword: str, node_type: str | None = None) -> list[dict[str, Any]]:
        """关键词搜索节点（模糊匹配名称和别名）"""
        keyword_lower = keyword.lower()
        results: list[dict] = []

        for node_id in self.graph.nodes:
            node_data = self.get_node(node_id)
            if not node_data:
                continue

            if node_type and node_data.get("type") != node_type:
                continue

            name = node_data.get("name", "").lower()
            brands = [b.lower() for b in node_data.get("brand_names", [])]

            if keyword_lower in name or any(keyword_lower in b for b in brands):
                results.append(node_data)

        return results

    def get_stats(self) -> dict[str, Any]:
        """获取图谱统计信息"""
        type_counts = defaultdict(int)
        for nid in self.graph.nodes:
            ntype = self.graph.nodes[nid].get("type", "Unknown")
            type_counts[ntype] += 1

        edge_type_counts = defaultdict(int)
        for _, _, data in self.graph.edges(data=True):
            edge_type_counts[data.get("type", "Unknown")] += 1

        return {
            "total_nodes": self.graph.number_of_nodes(),
            "total_edges": self.graph.number_of_edges(),
            "node_types": dict(type_counts),
            "edge_types": dict(edge_type_counts),
            "aliases_indexed": len(self._node_index),
        }


# ============================================================
# 模块级单例
# ============================================================

knowledge_graph = KnowledgeGraph()
