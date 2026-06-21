"""
工具注册中心 — 管理 MCP Client 生命周期，工具发现与格式转换

职责：
  1. 启动 MCP Server 子进程（stdio 通信）
  2. 获取 MCP 工具列表，转换为 OpenAI Function Calling 格式
  3. 提供 call_tool() 接口供 ReAct 循环调用
"""
from __future__ import annotations
import asyncio
import logging
import sys
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from src.react.schemas import ToolDef

logger = logging.getLogger("tool-registry")


class ToolRegistry:
    """单例模式的工具注册中心"""

    def __init__(self) -> None:
        self._session: ClientSession | None = None
        self._read = None
        self._write = None
        self._context_stack = None  # 保存 AsyncExitStack 引用
        self._tools: list[dict[str, Any]] = []  # OpenAI 格式的工具列表
        self._lock = asyncio.Lock()

    # ---------------------------------------------------------------
    # 连接管理
    # ---------------------------------------------------------------

    async def connect(self) -> None:
        """启动 MCP Server 子进程并建立 stdio 连接"""
        async with self._lock:
            if self._session is not None:
                logger.info("ToolRegistry already connected, skipping")
                return

            server_params = StdioServerParameters(
                command=sys.executable,  # python
                args=["-m", "src.mcp.mcp_server"],
            )

            # 使用 AsyncExitStack 管理嵌套的异步上下文管理器
            self._context_stack = AsyncExitStack()
            # stdio_client 是异步上下文管理器，yields (read, write)
            self._read, self._write = await self._context_stack.enter_async_context(
                stdio_client(server_params)
            )

            # 创建 ClientSession
            session_ctx = ClientSession(self._read, self._write)
            self._session = await self._context_stack.enter_async_context(session_ctx)
            await self._session.initialize()

            # 获取工具列表并转换格式
            tools_result = await self._session.list_tools()
            self._tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description or "",
                        "parameters": t.inputSchema if t.inputSchema else {},
                    },
                }
                for t in tools_result.tools
            ]

            logger.info(
                "ToolRegistry connected, %d tools loaded: %s",
                len(self._tools),
                [t["function"]["name"] for t in self._tools],
            )

    async def disconnect(self) -> None:
        """断开 MCP 连接，关闭子进程"""
        async with self._lock:
            if self._context_stack is not None:
                await self._context_stack.aclose()
                self._context_stack = None
            self._session = None
            self._read = None
            self._write = None
            self._tools.clear()
            logger.info("ToolRegistry disconnected")

    # ---------------------------------------------------------------
    # 工具访问
    # ---------------------------------------------------------------

    @property
    def tools(self) -> list[dict[str, Any]]:
        """返回 OpenAI Function Calling 格式的工具列表"""
        return list(self._tools)

    @property
    def is_connected(self) -> bool:
        return self._session is not None

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """调用 MCP 工具并返回文本结果"""
        if self._session is None:
            raise RuntimeError("ToolRegistry not connected — call connect() first")

        result = await self._session.call_tool(name, arguments)

        # 提取文本内容
        if result.content and len(result.content) > 0:
            return result.content[0].text
        return str(result)

    async def health_check(self) -> bool:
        """检查 MCP Server 是否存活"""
        try:
            if self._session is None:
                return False
            # 尝试列举工具作为心跳检测
            await self._session.list_tools()
            return True
        except Exception:
            return False


# ============================================================
# 模块级单例
# ============================================================

tool_registry = ToolRegistry()
