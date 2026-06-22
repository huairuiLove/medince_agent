"""SSE chat service — ReAct loop with role-based prompts and fallback."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import AsyncGenerator

from src.react.react_loop import run_react_loop
from src.react.schemas import ChatMessage, ChatRequest, ErrorEvent, TokenEvent, ToolEvent
from src.react.state_machine import state_machine
from src.react.system_prompt import get_system_messages
from src.react.tool_registry import tool_registry
from src.react.yuan_config import config
from src.yuan_fallback.local_db import offline_drug_check
from src.yuan_fallback.rule_engine import check_interactions_by_rules

logger = logging.getLogger("chat-service")


def extract_citations(tool_results: list[dict]) -> list[dict]:
    """Parse structured citations from tool call results."""
    citations: list[dict] = []
    cid = 0

    for tr in tool_results:
        result_text = tr.get("result", "")
        tool_name = tr.get("name", "")

        if any(k in tool_name for k in ("interaction", "review", "contraindication", "graph_rag")):
            for match in re.finditer(
                r"(?:###\s*)?(.+?)\s*[↔]\s*(.+?)\s*\[(.+?)\]",
                result_text,
            ):
                cid += 1
                drug_a = match.group(1).replace("**", "").strip()
                drug_b = match.group(2).replace("**", "").strip()
                sev = match.group(3)
                citations.append({
                    "id": f"cite_{cid}",
                    "source_type": "kg_edge",
                    "drug_a": drug_a,
                    "drug_b": drug_b,
                    "severity": sev,
                    "confidence": 0.90,
                    "citation_text": f"{drug_a} ↔ {drug_b} [{sev}]",
                })

        if "rule_fallback" in tool_name or "规则引擎" in result_text:
            for match in re.finditer(
                r"###\s*(.+?)\s*[↔]\s*(.+?)\s*\[(.+?)\]",
                result_text,
            ):
                cid += 1
                citations.append({
                    "id": f"cite_{cid}",
                    "source_type": "rule",
                    "drug_a": match.group(1).strip(),
                    "drug_b": match.group(2).strip(),
                    "severity": match.group(3),
                    "evidence_level": "B",
                    "confidence": 0.85,
                    "citation_text": f"[规则引擎] {match.group(1).strip()} ↔ {match.group(2).strip()}",
                })

    return citations


async def chat_event_stream(req: ChatRequest) -> AsyncGenerator[str, None]:
    """Generate SSE events for a chat request."""
    try:
        await state_machine.evaluate()
        level = state_machine.current_level
        user_msg = req.messages[-1].content if req.messages else ""
        role = req.role or "patient"

        yield (
            f"event: system\ndata: "
            f"{json.dumps({'level': level, 'description': state_machine.get_mode_description()}, ensure_ascii=False)}\n\n"
        )

        if level in ("rule_fallback", "offline"):
            result_text = (
                check_interactions_by_rules(user_msg)
                if level == "rule_fallback"
                else offline_drug_check(user_msg)
            )
            prefix = f"**[{state_machine.get_mode_description()}]**\n\n"
            result_text = prefix + result_text
            for char in result_text:
                yield f"event: token\ndata: {json.dumps({'token': char}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.002)
            yield "event: done\ndata: {}\n\n"
            return

        system_msgs = get_system_messages(role)
        system_chat_msgs = [
            ChatMessage(role=m["role"], content=m["content"])
            for m in system_msgs
        ]
        all_messages = system_chat_msgs + req.messages
        tool_results: list[dict] = []

        try:
            async for event in run_react_loop(all_messages):
                if isinstance(event, TokenEvent):
                    yield f"event: token\ndata: {event.model_dump_json()}\n\n"
                elif isinstance(event, ToolEvent):
                    yield f"event: tool\ndata: {event.model_dump_json()}\n\n"
                    if event.status == "done" and event.result:
                        tool_results.append(event.model_dump())
                elif isinstance(event, ErrorEvent):
                    yield f"event: error\ndata: {event.model_dump_json()}\n\n"
                elif isinstance(event, dict) and event.get("type") == "done":
                    if tool_results:
                        citations = extract_citations(tool_results)
                        if citations:
                            yield (
                                f"event: citation\ndata: "
                                f"{json.dumps({'citations': citations}, ensure_ascii=False)}\n\n"
                            )
                    yield "event: done\ndata: {}\n\n"
                    await state_machine.report_llm_success()
                    return
        except Exception as llm_exc:
            logger.error("LLM call failed: %s", llm_exc)
            await state_machine.report_llm_failure()
            yield f"event: error\ndata: {json.dumps({'message': f'AI 服务暂时不可用，已切换到本地规则引擎：{llm_exc}'}, ensure_ascii=False)}\n\n"
            result_text = check_interactions_by_rules(user_msg)
            for char in result_text:
                yield f"event: token\ndata: {json.dumps({'token': char}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.002)
            yield "event: done\ndata: {}\n\n"

    except asyncio.CancelledError:
        logger.info("SSE stream cancelled by client")
    except Exception as exc:
        logger.exception("SSE stream fatal error")
        yield f"event: error\ndata: {json.dumps({'message': str(exc)}, ensure_ascii=False)}\n\n"
        yield "event: done\ndata: {}\n\n"


async def init_chat_services() -> None:
    """Initialize MCP, local DB, and state machine on startup."""
    from src.yuan_fallback.local_db import init_local_db

    try:
        init_local_db()
        logger.info("Local fallback DB initialized")
    except Exception as exc:
        logger.warning("Local DB init failed (non-fatal): %s", exc)

    if not config.is_configured:
        await state_machine.report_llm_failure()
        logger.warning("Chat LLM not configured — rule engine fallback when evaluated")

    try:
        await tool_registry.connect()
        await state_machine.report_mcp_success()
        logger.info("MCP ToolRegistry connected, %d tools", len(tool_registry.tools))
    except Exception as exc:
        logger.error("Failed to connect MCP ToolRegistry: %s", exc)
        await state_machine.report_mcp_failure()

    await state_machine.evaluate()
    logger.info(
        "Chat system level: %s — %s",
        state_machine.current_level,
        state_machine.get_mode_description(),
    )


async def shutdown_chat_services() -> None:
    try:
        await tool_registry.disconnect()
    except Exception:
        pass
