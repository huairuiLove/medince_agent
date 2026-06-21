"""
MCP Server — 工具注册与执行
通过 stdio 与 FastAPI（MCP Client）通信

启动方式（独立进程）：
    python -m server.mcp.mcp_server

或由 FastAPI 作为子进程 spawn。
"""
from __future__ import annotations
import asyncio
import logging
import sys

# MCP SDK 导入
from mcp.server.fastmcp import FastMCP

# 工具实现
from src.mcp.tools.time_utils import get_current_time
from src.mcp.tools.knowledge import (
    retrieve_knowledge,
    list_knowledge_documents,
    load_seed_knowledge,
)
from src.mcp.tools.drug_query import (
    search_drug_info,
    check_drug_interactions,
    graph_rag_search,
    get_kg_stats,
)
from src.mcp.tools.prescription_safety import (
    review_prescription,
    check_patient_contraindications,
    find_safer_alternatives,
)

# 知识图谱
from src.graph_rag.knowledge_graph import knowledge_graph

logger = logging.getLogger("mcp-server")
logging.basicConfig(level=logging.INFO, stream=sys.stderr)

# ============================================================
# 创建 MCP Server 实例
# ============================================================

mcp = FastMCP(
    name="medsafe-mcp-server",
    instructions="MedSafe MCP Server — 用药安全 Graph RAG 工具集",
)


# ============================================================
# 通用工具
# ============================================================

@mcp.tool()
def get_current_time_tool() -> str:
    """获取当前系统时间（中文格式，含星期）"""
    return get_current_time()


@mcp.tool()
def list_knowledge_documents_tool() -> str:
    """查看当前已导入知识库的所有文档及其分块数量"""
    return list_knowledge_documents()


# ============================================================
# Phase 1 向量检索工具（保留兼容）
# ============================================================

@mcp.tool()
async def retrieve_knowledge_tool(query: str, top_k: int = 3) -> str:
    """从知识库中语义检索与查询最相关的文档片段（向量相似度），返回 top_k 条结果

    Args:
        query: 检索查询文本
        top_k: 返回结果数量，默认 3
    """
    result = await retrieve_knowledge(query, top_k)
    return result


# ============================================================
# Phase 2 Graph RAG 工具 — 用药安全核心
# ============================================================

@mcp.tool()
def search_drug_info_tool(drug_name: str) -> str:
    """查询单个药品的完整安全信息，包括适应症、禁忌症、已知药物相互作用、食物禁忌等。
    用于患者或医生查询特定药物的安全性。

    Args:
        drug_name: 药物通用名或商品名（如"华法林"、"阿莫西林"、"波立维"、"芬必得"）
    """
    return search_drug_info(drug_name)


@mcp.tool()
def check_drug_interactions_tool(drug_list: str) -> str:
    """检查一组药物/保健品/食物之间是否存在相互作用。
    支持处方药、OTC、保健品混合检查。
    这是用药安全的核心工具——当用户同时服用多种药物或保健品时必须使用。

    Args:
        drug_list: 待检查的药物名称，多个以逗号或顿号分隔，如"华法林, 布洛芬, 鱼油, 酒精"
    """
    return check_drug_interactions(drug_list)


@mcp.tool()
def graph_rag_search_tool(query: str) -> str:
    """综合用药安全分析：基于知识图谱的实体链接、子图检索和路径推理。
    适用于复杂的用药咨询场景，如"我有高血压和痛风，能吃布洛芬吗？"

    Args:
        query: 自然语言描述的用药安全查询
    """
    return graph_rag_search(query)


@mcp.tool()
def get_knowledge_graph_stats_tool() -> str:
    """获取当前药物知识图谱的统计信息（覆盖多少药物、多少相互作用等）"""
    return get_kg_stats()


# ============================================================
# Phase 3 专用分析工具 — 处方审查 / 禁忌排查 / 替代推荐
# ============================================================

@mcp.tool()
def review_prescription_tool(
    drug_list: str,
    patient_age: int = 0,
    patient_conditions: str = "",
    is_pregnant: str = "否",
    is_lactating: str = "否",
    kidney_function: str = "normal",
    liver_function: str = "normal",
) -> str:
    """处方综合安全性审查——检查一组药物的所有潜在安全问题。

    这是最全面的用药安全分析工具。同时分析药物-药物相互作用、患者禁忌症匹配、
    特殊人群风险、食物禁忌等。当用户需要综合评估一个处方或用药方案时优先使用。

    Args:
        drug_list: 药物列表，逗号分隔（如"华法林, 阿司匹林, 布洛芬"）
        patient_age: 患者年龄（0表示未知）
        patient_conditions: 现有疾病，逗号分隔（如"高血压, 糖尿病"）
        is_pregnant: 是否妊娠 (是/否)
        is_lactating: 是否哺乳期 (是/否)
        kidney_function: 肾功能 (normal/mild_impaired/severe_impaired)
        liver_function: 肝功能 (normal/mild_impaired/severe_impaired)
    """
    return review_prescription(
        drug_list, patient_age, patient_conditions,
        is_pregnant, is_lactating, kidney_function, liver_function
    )


@mcp.tool()
def check_patient_contraindications_tool(
    drug_name: str,
    patient_conditions: str = "",
    patient_age: int = 0,
    is_pregnant: str = "否",
    is_lactating: str = "否",
    kidney_function: str = "normal",
    liver_function: str = "normal",
) -> str:
    """针对特定患者，深度检查某个药物的所有禁忌症和慎用情况。
    当用户询问"XX药我能吃吗"或需要根据患者情况评估某药物安全性时使用。

    Args:
        drug_name: 药物名称
        patient_conditions: 患者疾病列表
        patient_age: 年龄
        is_pregnant: 是否妊娠
        is_lactating: 是否哺乳
        kidney_function: 肾功能
        liver_function: 肝功能
    """
    return check_patient_contraindications(
        drug_name, patient_conditions, patient_age,
        is_pregnant, is_lactating, kidney_function, liver_function
    )


@mcp.tool()
def find_safer_alternatives_tool(
    drug_name: str,
    patient_conditions: str = "",
    patient_age: int = 0,
    is_pregnant: str = "否",
    reason: str = "",
) -> str:
    """当某药物存在安全性问题时，基于药物类别知识推荐可能更安全的替代方案。
    在发现严重相互作用或禁忌症后，帮助用户了解有哪些可选替代药物。

    Args:
        drug_name: 需要替换的药物名称
        patient_conditions: 患者疾病
        patient_age: 年龄
        is_pregnant: 是否妊娠
        reason: 替换原因（如"出血风险"、"肝功能异常"）
    """
    return find_safer_alternatives(
        drug_name, patient_conditions, patient_age, is_pregnant, reason
    )


# ============================================================
# 启动入口
# ============================================================

async def run_mcp_server() -> None:
    """以 stdio 传输方式启动 MCP Server"""
    logger.info("MCP Server starting on stdio...")

    # 加载 Graph RAG 知识图谱
    try:
        count = knowledge_graph.load_from_json()
        logger.info("Knowledge graph loaded: %d nodes", count)
    except Exception as exc:
        logger.error("Failed to load knowledge graph: %s", exc)

    # 加载种子知识（向量 RAG 文档）
    try:
        count = load_seed_knowledge()
        if count > 0:
            logger.info("Loaded %d seed knowledge chunks", count)
    except Exception as exc:
        logger.warning("Failed to load seed knowledge: %s", exc)

    # 使用 stdio 传输运行
    await mcp.run_stdio_async()


def main() -> None:
    """控制台入口"""
    asyncio.run(run_mcp_server())


if __name__ == "__main__":
    main()
