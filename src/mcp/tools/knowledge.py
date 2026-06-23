"""
知识库工具：文档分块、Embedding 生成、语义检索、文档列表
"""
from __future__ import annotations
from typing import Any
import json
from pathlib import Path
from src.llm.embedding_client import embed_text_async
from src.llm.errors import LLMNotConfiguredError
from src.react.yuan_config import config


# ============================================================
# 全局状态（文档 + 分块 + embedding 缓存）
# ============================================================

class KnowledgeState:
    """知识库内存状态，存文档元信息、分块文本、embedding 向量"""

    def __init__(self) -> None:
        self.documents: list[dict[str, Any]] = []
        self.chunks: list[dict[str, Any]] = []

    def add_document(self, name: str, text: str, source: str | None = None) -> int:
        """添加文档，返回分块数量"""
        chunks = chunk_text(text, config.CHUNK_SIZE, config.CHUNK_OVERLAP)
        doc_entry = {
            "name": name,
            "source": source,
            "chunk_count": len(chunks),
        }
        self.documents.append(doc_entry)

        for i, chunk in enumerate(chunks):
            self.chunks.append({
                "documentName": name,
                "chunkIndex": i,
                "text": chunk,
                "embedding": None,  # 延迟计算
            })
        return len(chunks)

    def clear(self) -> None:
        self.documents.clear()
        self.chunks.clear()


# 模块级单例
knowledge_state = KnowledgeState()


# ============================================================
# 文本分块
# ============================================================

def chunk_text(text: str, chunk_size: int = 900, overlap: int = 160) -> list[str]:
    """滑动窗口分块"""
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        value = text[start:end].strip()
        if value:
            chunks.append(value)
        start += chunk_size - overlap
    return chunks


# ============================================================
# Embedding 生成
# ============================================================

async def get_embedding(text: str) -> list[float]:
    """调用 embedding 服务（LM Studio / OpenAI 兼容 API 或本地模型）"""
    return await embed_text_async(text, kind="passage")


# ============================================================
# 余弦相似度
# ============================================================

def cosine_similarity(a: list[float], b: list[float]) -> float:
    """计算两个向量的余弦相似度"""
    length = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(length))
    norm_a = sum(x * x for x in a[:length])
    norm_b = sum(x * x for x in b[:length])
    if not norm_a or not norm_b:
        return 0.0
    return dot / ((norm_a ** 0.5) * (norm_b ** 0.5))


# ============================================================
# 检索
# ============================================================

async def retrieve_knowledge(query: str, top_k: int = 3) -> str:
    """从知识库语义检索相关内容"""
    state = knowledge_state

    if not state.chunks:
        return "知识库为空，请先上传文档。"

    try:
        for chunk in state.chunks:
            if chunk["embedding"] is None:
                chunk["embedding"] = await get_embedding(chunk["text"])
        query_emb = await get_embedding(query)
    except LLMNotConfiguredError as exc:
        return f"Embedding 未配置，无法检索：{exc}"

    # 相似度排序，取 top_k
    scored = []
    for chunk in state.chunks:
        score = cosine_similarity(query_emb, chunk["embedding"])
        scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_k]

    lines: list[str] = []
    for i, (score, chunk) in enumerate(top, 1):
        pct = score * 100
        lines.append(
            f"[{i}] 来源: {chunk['documentName']}\n"
            f"相关度: {pct:.1f}%\n"
            f"内容: {chunk['text']}"
        )

    return "\n\n".join(lines) if lines else "未找到相关内容"


def list_knowledge_documents() -> str:
    """列出已导入的知识库文档"""
    docs = knowledge_state.documents
    if not docs:
        return "知识库为空"

    lines = [f"- {d['name']} ({d['chunk_count']} 片段)" for d in docs]
    return "已导入文档:\n" + "\n".join(lines)


# ============================================================
# 从文件加载种子知识库
# ============================================================

def load_seed_knowledge(data_dir: str | None = None) -> int:
    """从 data/ 目录加载种子知识（如果存在）"""
    if data_dir is None:
        data_dir = str(Path(__file__).resolve().parent.parent.parent.parent / "data")

    total = 0
    data_path = Path(data_dir)

    # 尝试加载 JSON 知识文件
    for pattern in ["*.json", "*.txt", "*.md"]:
        for file_path in data_path.glob(pattern):
            try:
                text = file_path.read_text(encoding="utf-8")
                name = file_path.name
                n = knowledge_state.add_document(name, text, source=str(file_path))
                total += n
            except Exception:
                pass

    return total
