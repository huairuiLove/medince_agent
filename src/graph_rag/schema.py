"""
知识图谱 Schema 定义

Node 类型:
  Drug          — 药物（通用名/商品名/ATC分类/剂型）
  Ingredient    — 成分（化学药/中成药/保健品）
  Condition     — 适应症/禁忌症
  Population    — 特殊人群（孕妇/哺乳期/老人/儿童/肝肾功能不全）
  Food          — 食物/饮品
  Enzyme        — 代谢酶（CYP450家族等）

Edge 类型:
  HAS_INGREDIENT         — Drug → Ingredient
  INTERACTS_WITH         — Drug ↔ Drug（带 severity + mechanism）
  CONTRAINDICATED_FOR    — Drug → Condition/Population
  INDICATED_FOR          — Drug → Condition
  FOOD_INTERACTION       — Drug ↔ Food
  METABOLIZED_BY         — Drug → Enzyme
  BELONGS_TO_CLASS       — Drug → DrugClass
"""
from __future__ import annotations
from enum import Enum
from dataclasses import dataclass, field
from typing import Any


# ============================================================
# 节点类型
# ============================================================

class NodeType(str, Enum):
    DRUG = "Drug"
    INGREDIENT = "Ingredient"
    CONDITION = "Condition"
    POPULATION = "Population"
    FOOD = "Food"
    ENZYME = "Enzyme"
    DRUG_CLASS = "DrugClass"


# ============================================================
# 边类型
# ============================================================

class EdgeType(str, Enum):
    HAS_INGREDIENT = "HAS_INGREDIENT"
    INTERACTS_WITH = "INTERACTS_WITH"
    CONTRAINDICATED_FOR = "CONTRAINDICATED_FOR"
    INDICATED_FOR = "INDICATED_FOR"
    FOOD_INTERACTION = "FOOD_INTERACTION"
    METABOLIZED_BY = "METABOLIZED_BY"
    BELONGS_TO_CLASS = "BELONGS_TO_CLASS"


# ============================================================
# 严重程度
# ============================================================

class Severity(str, Enum):
    MILD = "mild"               # 轻微（注意即可）
    MODERATE = "moderate"       # 中等（需调整剂量或监测）
    SEVERE = "severe"           # 严重（禁止联用）
    CONTRAINDICATED = "contraindicated"  # 绝对禁忌


# ============================================================
# 节点属性模型
# ============================================================

@dataclass
class DrugNode:
    name: str                          # 通用名
    brand_names: list[str] = field(default_factory=list)  # 商品名
    atc_code: str = ""                 # ATC 分类码
    category: str = ""                 # 药物类别
    rx_type: str = ""                  # 处方药(Rx) / 非处方药(OTC)
    description: str = ""              # 简要说明


@dataclass
class InteractionEdge:
    severity: Severity = Severity.MODERATE
    mechanism: str = ""                # 作用机制
    effect: str = ""                   # 相互作用后果
    recommendation: str = ""           # 建议措施
    evidence_level: str = ""           # 证据等级 (A/B/C/D)


# ============================================================
# 图谱查询结果
# ============================================================

@dataclass
class SubgraphResult:
    """子图检索结果"""
    center_node: str                   # 中心节点名
    center_type: str                   # 中心节点类型
    nodes: list[dict[str, Any]]        # 子图节点列表
    edges: list[dict[str, Any]]        # 子图边列表
    hop_count: int                     # 检索跳数


@dataclass
class PathResult:
    """路径推理结果"""
    source: str                        # 起始节点
    target: str                        # 目标节点
    paths: list[list[str]]             # 所有路径（每条路径是节点名列表）
    path_count: int                    # 路径总数
    shortest_length: int               # 最短路径长度
