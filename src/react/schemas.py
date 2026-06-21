"""
Pydantic 数据模型 — 请求/响应/内部状态的结构定义
"""
from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field


# ============================================================
# 对话相关
# ============================================================

class ChatMessage(BaseModel):
    """单条对话消息"""
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    tool_call_id: str | None = None
    name: str | None = None


class ChatRequest(BaseModel):
    """POST /api/chat/stream 请求体"""
    messages: list[ChatMessage]
    stream: bool = Field(default=True, description="是否流式返回")
    role: str = Field(default="patient", description="用户角色: doctor / patient")


# ============================================================
# 工具调用相关（OpenAI Function Calling 格式）
# ============================================================

class FunctionCall(BaseModel):
    """LLM 返回的工具调用——函数名+参数"""
    name: str
    arguments: str  # JSON 字符串


class ToolCall(BaseModel):
    """LLM 返回的单条工具调用"""
    id: str
    type: Literal["function"] = "function"
    function: FunctionCall


class FunctionDef(BaseModel):
    """工具函数定义（OpenAI tools 数组中的 function 字段）"""
    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class ToolDef(BaseModel):
    """完整的工具定义项"""
    type: Literal["function"] = "function"
    function: FunctionDef


# ============================================================
# SSE 事件数据
# ============================================================

class TokenEvent(BaseModel):
    token: str


class ToolEvent(BaseModel):
    id: str
    name: str
    args: dict[str, Any]
    status: Literal["calling", "done", "error"]
    result: str | None = None


class ErrorEvent(BaseModel):
    message: str


class DoneEvent(BaseModel):
    pass


# ============================================================
# 状态机降级（Phase 4 完善）
# ============================================================

class SystemState(BaseModel):
    level: Literal["full", "llm_only", "rule_fallback", "offline"] = "full"
    llm_available: bool = True
    kg_available: bool = True
    mcp_available: bool = True


# ============================================================
# 知识库文档
# ============================================================

class DocumentMeta(BaseModel):
    name: str
    chunk_count: int
    source: str | None = None
