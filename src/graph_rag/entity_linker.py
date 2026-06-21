"""
实体链接器 — 从自然语言中抽取药物/食物/病症实体，映射到知识图谱节点

策略（难度递增，当前实现 L0+L1）：
  L0: 精确匹配 — 名称/别名直接命中图谱节点
  L1: 模糊匹配 — 基于子串包含和编辑距离
  L2: LLM NER — 调用 LLM 做命名实体识别
"""
from __future__ import annotations
import re
import logging
from dataclasses import dataclass, field
from typing import Any

from src.graph_rag.knowledge_graph import knowledge_graph

logger = logging.getLogger("entity-linker")


@dataclass
class LinkedEntity:
    """链接结果"""
    mention: str                       # 原文中的提及文本
    node_id: str                       # 图谱节点 ID
    node_name: str                     # 规范名称
    node_type: str                     # 节点类型
    confidence: float                  # 置信度 0~1
    match_method: str = "exact"        # exact / substring / fuzzy


@dataclass
class LinkingResult:
    """一次链接的完整结果"""
    entities: list[LinkedEntity] = field(default_factory=list)
    unrecognized: list[str] = field(default_factory=list)  # 未识别的提及


class EntityLinker:
    """药物实体链接器"""

    # 药物相关的中文触发词（帮助 LLM/NER 识别）
    DRUG_TRIGGERS = [
        "药", "片", "胶囊", "颗粒", "口服液", "注射液", "素", "霉素",
        "地平", "普利", "沙坦", "他汀", "洛尔", "唑", "西汀", "泮",
        "匹林", "芬", "替丁", "拉唑",
    ]

    def __init__(self) -> None:
        pass

    # ---------------------------------------------------------------
    # 主入口
    # ---------------------------------------------------------------

    def link(self, text: str) -> LinkingResult:
        """对输入文本做实体链接"""
        result = LinkingResult()

        # L0: 精确匹配（在已索引的别名表中查找）
        exact_matches = self._exact_match(text)
        result.entities.extend(exact_matches)

        # L1: 子串匹配（对尚未匹配的部分）
        matched_mentions = {e.mention for e in result.entities}
        substring_matches = self._substring_match(text, exclude=matched_mentions)
        result.entities.extend(substring_matches)

        # 收集未识别的可能药物提及（简单启发式）
        result.unrecognized = self._find_unrecognized(text, result.entities)

        logger.debug(
            "Entity linking: %d entities found, %d unrecognized",
            len(result.entities), len(result.unrecognized),
        )
        return result

    # ---------------------------------------------------------------
    # L0: 精确匹配
    # ---------------------------------------------------------------

    def _exact_match(self, text: str) -> list[LinkedEntity]:
        """在文本中查找精确匹配的图谱节点名/别名"""
        results: list[LinkedEntity] = []
        text_lower = text.lower()
        seen_nodes: set[str] = set()

        # 按别名长度降序排列（优先长匹配，避免"阿司匹林"匹配到"阿司匹林(小剂量)"的一部分）
        aliases = sorted(
            knowledge_graph._node_index.items(),
            key=lambda x: len(x[0]),
            reverse=True,
        )

        for alias, node_id in aliases:
            if node_id in seen_nodes:
                continue
            if alias in text_lower:
                node = knowledge_graph.get_node(node_id)
                if node:
                    results.append(LinkedEntity(
                        mention=alias,
                        node_id=node_id,
                        node_name=node.get("name", alias),
                        node_type=node.get("type", ""),
                        confidence=1.0,
                        match_method="exact",
                    ))
                    seen_nodes.add(node_id)

        return results

    # ---------------------------------------------------------------
    # L1: 子串匹配
    # ---------------------------------------------------------------

    def _substring_match(
        self, text: str, exclude: set[str]
    ) -> list[LinkedEntity]:
        """对图谱中的短名称做子串包含匹配"""
        results: list[LinkedEntity] = []
        text_lower = text.lower()
        seen_nodes: set[str] = set()

        # 只对短别名（≤4字）做子串匹配
        for alias, node_id in knowledge_graph._node_index.items():
            if node_id in seen_nodes:
                continue
            if len(alias) <= 4 and alias in text_lower:
                # 检查是否已经被精确匹配覆盖
                node = knowledge_graph.get_node(node_id)
                if node and node.get("name", "").lower() not in exclude:
                    results.append(LinkedEntity(
                        mention=alias,
                        node_id=node_id,
                        node_name=node.get("name", alias),
                        node_type=node.get("type", ""),
                        confidence=0.7,
                        match_method="substring",
                    ))
                    seen_nodes.add(node_id)

        return results

    # ---------------------------------------------------------------
    # 启发式未识别词汇收集
    # ---------------------------------------------------------------

    def _find_unrecognized(
        self, text: str, entities: list[LinkedEntity]
    ) -> list[str]:
        """找出文本中可能包含药物但未匹配到的片段"""
        matched_texts = {e.mention for e in entities}
        unrecognized: list[str] = []

        # 简单规则：包含药物触发词的短片段
        for trigger in self.DRUG_TRIGGERS:
            if trigger in text:
                # 找到触发词周围的词
                for match in re.finditer(rf"\S*{trigger}\S*", text):
                    word = match.group()
                    if word not in matched_texts and len(word) >= 2:
                        unrecognized.append(word)

        return unrecognized


# ============================================================
# 工具函数
# ============================================================

def link_drugs(text: str) -> LinkingResult:
    """快捷函数：从文本链接药物实体"""
    linker = EntityLinker()
    return linker.link(text)


# 模块级单例
entity_linker = EntityLinker()
