"""
ReAct 循环编排 — 两阶段 LLM 调用 + 工具执行

流程：
  1. 第一次 LLM 调用（非流式，携带工具列表）→ 模型决定是否调用工具
  2. 若返回 tool_calls → 通过 MCP 执行对应工具
  3. 将工具结果回填到对话历史
  4. 第二次 LLM 调用（流式）→ 基于工具结果生成最终回复

这是整个 Agent 的核心推理引擎。
"""
from __future__ import annotations
import asyncio
import json
import logging
from typing import Any, AsyncGenerator

import httpx

from src.react.yuan_config import config
from src.react.tool_registry import tool_registry
from src.react.schemas import (
    ChatMessage,
    TokenEvent,
    ToolEvent,
    ErrorEvent,
)

logger = logging.getLogger("react-loop")


# ============================================================
# LLM API 调用封装
# ============================================================

def _build_body(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    stream: bool,
) -> dict[str, Any]:
    """构建 LLM API 请求体"""
    body: dict[str, Any] = {
        "model": config.DEEPSEEK_MODEL,
        "messages": messages,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    body["stream"] = stream
    return body


def _headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.DEEPSEEK_API_KEY}",
    }


async def _stream_response(response: httpx.Response) -> AsyncGenerator[str, None]:
    """从流式响应中逐 token 提取内容"""
    buffer = ""
    async for chunk in response.aiter_bytes():
        buffer += chunk.decode("utf-8", errors="replace")
        lines = buffer.split("\n")
        buffer = lines.pop() if lines else ""

        for line in lines:
            line = line.strip()
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                return
            try:
                parsed = json.loads(data_str)
                content = (
                    parsed.get("choices", [{}])[0]
                    .get("delta", {})
                    .get("content", "")
                )
                if content:
                    yield content
            except (json.JSONDecodeError, KeyError, IndexError):
                continue


# ============================================================
# ReAct 主循环（异步生成器）
# ============================================================

async def run_react_loop(
    messages: list[ChatMessage],
) -> AsyncGenerator[TokenEvent | ToolEvent | ErrorEvent | dict[str, Any], None]:
    """
    ReAct 推理循环的异步生成器

    Yields:
        ToolEvent — 工具调用状态变更
        TokenEvent — 流式 token
        {"type": "done"} — 对话结束
        ErrorEvent — 错误
    """

    # 获取可用工具列表
    tools = tool_registry.tools if tool_registry.is_connected else []

    # 将消息转为 dict 列表
    msg_dicts = [m.model_dump(exclude_none=True) for m in messages]

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(config.LLM_TIMEOUT)
    ) as client:

        # ================================================================
        # 第一次 LLM 调用（非流式）—— 决定是否需要工具
        # ================================================================
        try:
            if config.is_mock:
                yield ErrorEvent(message="Mock 模式：未配置 LLM API Key")
                yield {"type": "done"}
                return

            url = f"{config.DEEPSEEK_BASE_URL}/chat/completions"
            hdrs = _headers()
            body = _build_body(msg_dicts, tools, stream=False)
            first_resp = await client.post(url, headers=hdrs, json=body)
            first_resp.raise_for_status()
            first_data = first_resp.json()
        except Exception as exc:
            logger.error("First LLM call failed: %s", exc)
            yield ErrorEvent(message=f"模型调用失败: {exc}")
            yield {"type": "done"}
            return

        choice = first_data.get("choices", [{}])[0]
        message = choice.get("message", {})
        tool_calls = message.get("tool_calls")
        # 如果模型在 content 里也写了函数调用文本，清除掉避免显示乱码
        if tool_calls and message.get("content", "").strip():
            message["content"] = ""

        # ================================================================
        # 分支 A：不需要工具 → 直接流式生成回复
        # ================================================================
        if not tool_calls:
            try:
                stream_resp = await client.send(
                    client.build_request(
                        "POST",
                        f"{config.DEEPSEEK_BASE_URL}/chat/completions",
                        headers=_headers(),
                        json=_build_body(msg_dicts, None, stream=True),
                    ),
                    stream=True,
                )
                stream_resp.raise_for_status()
            except Exception as exc:
                logger.error("Fallback stream call failed: %s", exc)
                yield ErrorEvent(message=f"流式生成失败: {exc}")
                yield {"type": "done"}
                return

            async for token in _stream_response(stream_resp):
                yield TokenEvent(token=token)

            yield {"type": "done"}
            return

        # ================================================================
        # 分支 B：需要工具 → 逐个执行 → 回填 → 第二次流式生成
        # ================================================================
        conversation = list(msg_dicts)
        conversation.append(message)

        for tc in tool_calls:
            tool_id = tc.get("id", "")
            func = tc.get("function", {})
            tool_name = func.get("name", "")
            try:
                tool_args = json.loads(func.get("arguments", "{}"))
            except json.JSONDecodeError:
                tool_args = {}

            # 通知前端：开始调用工具
            yield ToolEvent(
                id=tool_id,
                name=tool_name,
                args=tool_args,
                status="calling",
            )

            # 执行 MCP 工具
            try:
                tool_result_text = await tool_registry.call_tool(
                    tool_name, tool_args
                )
                yield ToolEvent(
                    id=tool_id,
                    name=tool_name,
                    args=tool_args,
                    status="done",
                    result=tool_result_text,
                )
            except Exception as exc:
                logger.error("Tool '%s' execution failed: %s", tool_name, exc)
                tool_result_text = f"工具执行失败: {exc}"
                yield ToolEvent(
                    id=tool_id,
                    name=tool_name,
                    args=tool_args,
                    status="error",
                    result=tool_result_text,
                )

            # 工具结果回填
            conversation.append({
                "role": "tool",
                "content": tool_result_text,
                "tool_call_id": tool_id,
            })

        # ================================================================
        # 第二次 LLM 调用（流式）—— 基于工具结果生成最终回复
        # ================================================================
        try:
            final_stream = await client.send(
                client.build_request(
                    "POST",
                    f"{config.DEEPSEEK_BASE_URL}/chat/completions",
                    headers=_headers(),
                    json=_build_body(conversation, None, stream=True),
                ),
                stream=True,
            )
            final_stream.raise_for_status()
        except Exception as exc:
            logger.error("Second LLM call failed: %s", exc)
            yield ErrorEvent(message=f"生成最终回复失败: {exc}")
            yield {"type": "done"}
            return

        async for token in _stream_response(final_stream):
            yield TokenEvent(token=token)

        yield {"type": "done"}
