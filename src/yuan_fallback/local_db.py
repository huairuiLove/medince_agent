"""
本地 SQLite 数据库 — 最底层离线兜底

当 LLM API + KG + 规则引擎都不可用时，系统降级到此层。
预计算药物相互作用表和药物信息表，可脱离外部服务独立运行。

从 KG JSON 数据初始化 SQLite，提供只读查询。
"""
from __future__ import annotations
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger("local-db")

# 默认数据库路径
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "local_fallback.db"

# KG 种子数据路径（与 chat.knowledge_graph 一致）
def _default_kg_json_path() -> Path:
    from src.config import get_config, resolve_path

    cfg = get_config()
    rel = (
        cfg.get("chat", {}).get("knowledge_graph")
        or cfg.get("clinical_knowledge", {}).get("drug_kg_v2_path")
        or "datasets/knowledge/drug_kg_v2.json"
    )
    primary = resolve_path(rel)
    if primary.exists():
        return primary
    legacy = resolve_path("datasets/knowledge/drug_kg.json")
    return legacy if legacy.exists() else primary


KG_JSON_PATH = _default_kg_json_path()


# ============================================================
# 数据库初始化
# ============================================================

def init_local_db(db_path: str | Path | None = None) -> sqlite3.Connection:
    """初始化/重建本地 SQLite 数据库，从 KG JSON 种子数据填充"""
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")

    cursor = conn.cursor()

    # 创建表
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS drugs (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT,
            rx_type TEXT,
            description TEXT,
            brand_names TEXT
        );

        CREATE TABLE IF NOT EXISTS interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            drug_a TEXT NOT NULL,
            drug_b TEXT NOT NULL,
            edge_type TEXT NOT NULL,
            severity TEXT,
            mechanism TEXT,
            effect TEXT,
            recommendation TEXT,
            evidence_level TEXT
        );

        CREATE TABLE IF NOT EXISTS contraindications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            drug_name TEXT NOT NULL,
            target_name TEXT NOT NULL,
            target_type TEXT,
            severity TEXT,
            mechanism TEXT,
            recommendation TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_drugs_name ON drugs(name);
        CREATE INDEX IF NOT EXISTS idx_inter_drug_a ON interactions(drug_a);
        CREATE INDEX IF NOT EXISTS idx_inter_drug_b ON interactions(drug_b);
        CREATE INDEX IF NOT EXISTS idx_contra_drug ON contraindications(drug_name);
    """)

    # 检查是否需要填充种子数据
    count = cursor.execute("SELECT COUNT(*) FROM drugs").fetchone()[0]
    if count > 0:
        logger.info("Local DB already populated: %d drugs", count)
        conn.commit()
        return conn

    # 从 KG JSON 填充
    if not KG_JSON_PATH.exists():
        logger.warning("KG JSON not found at %s, local DB will be empty", KG_JSON_PATH)
        conn.commit()
        return conn

    with open(KG_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 填充 drugs 表
    for node in data.get("nodes", []):
        if node.get("type") == "Drug":
            cursor.execute(
                "INSERT OR REPLACE INTO drugs (id, name, category, rx_type, description, brand_names) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    node["id"],
                    node.get("name", ""),
                    node.get("category", ""),
                    node.get("rx_type", ""),
                    node.get("description", ""),
                    json.dumps(node.get("brand_names", []), ensure_ascii=False),
                ),
            )

    # 填充 interactions 表（边）
    for edge in data.get("edges", []):
        src_node = next((n for n in data["nodes"] if n["id"] == edge["source"]), None)
        tgt_node = next((n for n in data["nodes"] if n["id"] == edge["target"]), None)
        if not src_node or not tgt_node:
            continue

        etype = edge.get("type", "")
        if etype == "INTERACTS_WITH":
            cursor.execute(
                "INSERT INTO interactions (drug_a, drug_b, edge_type, severity, mechanism, "
                "effect, recommendation, evidence_level) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    src_node["name"], tgt_node["name"], etype,
                    edge.get("severity", ""), edge.get("mechanism", ""),
                    edge.get("effect", ""), edge.get("recommendation", ""),
                    edge.get("evidence_level", ""),
                ),
            )
        elif etype in ("CONTRAINDICATED_FOR",):
            cursor.execute(
                "INSERT INTO contraindications (drug_name, target_name, target_type, "
                "severity, mechanism, recommendation) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    src_node["name"], tgt_node["name"],
                    tgt_node.get("type", ""),
                    edge.get("severity", ""), edge.get("mechanism", ""),
                    edge.get("recommendation", ""),
                ),
            )

    conn.commit()

    drug_count = cursor.execute("SELECT COUNT(*) FROM drugs").fetchone()[0]
    inter_count = cursor.execute("SELECT COUNT(*) FROM interactions").fetchone()[0]
    contra_count = cursor.execute("SELECT COUNT(*) FROM contraindications").fetchone()[0]
    logger.info("Local DB initialized: %d drugs, %d interactions, %d contraindications",
                drug_count, inter_count, contra_count)

    return conn


# ============================================================
# 查询接口
# ============================================================

def get_db_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """获取数据库连接（如果 DB 不存在则初始化）"""
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    if not Path(db_path).exists():
        return init_local_db(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def query_drug(db_path: str | Path | None, drug_name: str) -> dict[str, Any] | None:
    """查询单个药物的基本信息"""
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM drugs WHERE name LIKE ? OR brand_names LIKE ? LIMIT 1",
            (f"%{drug_name}%", f"%{drug_name}%"),
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()


def query_interactions(
    db_path: str | Path | None, drug_names: list[str]
) -> list[dict[str, Any]]:
    """查询一组药物之间的所有已知相互作用"""
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        results = []
        for i, drug_a in enumerate(drug_names):
            for drug_b in drug_names[i + 1:]:
                cursor.execute(
                    "SELECT * FROM interactions WHERE "
                    "(drug_a LIKE ? AND drug_b LIKE ?) OR (drug_a LIKE ? AND drug_b LIKE ?)",
                    (f"%{drug_a}%", f"%{drug_b}%", f"%{drug_b}%", f"%{drug_a}%"),
                )
                for row in cursor.fetchall():
                    results.append(dict(row))
        return results
    finally:
        conn.close()


def query_contraindications(
    db_path: str | Path | None, drug_name: str
) -> list[dict[str, Any]]:
    """查询某药物的所有禁忌症"""
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM contraindications WHERE drug_name LIKE ?",
            (f"%{drug_name}%",),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def offline_drug_check(drug_list_str: str) -> str:
    """
    完全离线模式下的药物安全性检查（基于本地 SQLite）

    当 LLM、KG、规则引擎全部不可用时使用。
    """
    drugs = [d.strip() for d in drug_list_str.replace("、", ",").split(",") if d.strip()]

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        lines = [
            "## 离线模式 — 药物安全性查询",
            "",
            f"查询药物：{'、'.join(drugs)}",
            "",
            "> 🚨 系统当前处于离线模式（LLM + KG + 规则引擎均不可用）。",
            "> 以下结果来自本地静态数据库，信息可能不完整。",
            "> 紧急情况请拨打 120。",
            "",
        ]

        # 查药物信息
        for drug in drugs:
            cursor.execute(
                "SELECT * FROM drugs WHERE name LIKE ? OR brand_names LIKE ?",
                (f"%{drug}%", f"%{drug}%"),
            )
            row = cursor.fetchone()
            if row:
                r = dict(row)
                brands = json.loads(r.get("brand_names", "[]"))
                brands_str = f"（{'、'.join(brands)}）" if brands else ""
                lines.append(f"- **{r['name']}**{brands_str} — {r.get('category', '')} | {r.get('description', '')}")
            else:
                lines.append(f"- **{drug}** — 未收录")

        lines.append("")

        # 查相互作用
        found_any = False
        for i, d1 in enumerate(drugs):
            for d2 in drugs[i + 1:]:
                cursor.execute(
                    "SELECT * FROM interactions WHERE "
                    "(drug_a LIKE ? AND drug_b LIKE ?) OR (drug_a LIKE ? AND drug_b LIKE ?)",
                    (f"%{d1}%", f"%{d2}%", f"%{d2}%", f"%{d1}%"),
                )
                for row in cursor.fetchall():
                    found_any = True
                    r = dict(row)
                    lines.append(
                        f"### {r['drug_a']} ↔ {r['drug_b']} [{r.get('severity', '')}]\n"
                        f"- {r.get('mechanism', '')}\n"
                        f"- 建议: {r.get('recommendation', '')}"
                    )

        if not found_any:
            lines.append("✅ 离线数据库中未找到收录的药物相互作用。")

        return "\n".join(lines)
    finally:
        conn.close()
