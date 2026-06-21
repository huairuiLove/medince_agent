"""
状态机 — 动态降级容错

完整的四级降级体系，自动监测组件健康状态并切换运行模式：

  L0  FULL           — LLM + KG + MCP 全部可用 → 正常 ReAct 模式
  L1  LLM_ONLY       — KG 不可用 → 纯 LLM 推理（工具标注"无知识溯源"）
  L2  RULE_FALLBACK  — LLM 不可用 → 本地规则引擎兜底
  L3  OFFLINE        — 全部不可用 → SQLite 静态库离线查询

恢复策略：定时探测已失效组件，一旦恢复自动升回更高等级。
"""
from __future__ import annotations
import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum

from src.react.schemas import SystemState

logger = logging.getLogger("state-machine")


class FallbackLevel(str, Enum):
    FULL = "full"
    LLM_ONLY = "llm_only"
    RULE_FALLBACK = "rule_fallback"
    OFFLINE = "offline"


@dataclass
class ComponentHealth:
    name: str
    available: bool = True
    last_check: float = 0.0
    fail_count: int = 0
    max_fails: int = 3  # 连续失败 N 次后才标记为不可用
    check_interval: float = 60.0  # 健康检查间隔（秒）


class StateMachine:
    """系统降级状态机"""

    def __init__(self) -> None:
        self._state = SystemState()
        self._components = {
            "llm": ComponentHealth(name="LLM API", max_fails=2),
            "kg": ComponentHealth(name="Knowledge Graph", max_fails=2),
            "mcp": ComponentHealth(name="MCP Server", max_fails=3),
        }
        self._on_level_change: list[callable] = []
        self._last_level: str = FallbackLevel.FULL.value
        self._lock = asyncio.Lock()

    # ---------------------------------------------------------------
    # 属性
    # ---------------------------------------------------------------

    @property
    def current_level(self) -> str:
        return self._state.level

    @property
    def state(self) -> SystemState:
        return self._state

    # ---------------------------------------------------------------
    # 健康检查回调
    # ---------------------------------------------------------------

    def on_level_change(self, callback: callable) -> None:
        """注册降级级别变更回调"""
        self._on_level_change.append(callback)

    async def _notify_level_change(self, old_level: str, new_level: str) -> None:
        for cb in self._on_level_change:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(old_level, new_level)
                else:
                    cb(old_level, new_level)
            except Exception as exc:
                logger.error("Level change callback failed: %s", exc)

    # ---------------------------------------------------------------
    # 组件健康上报
    # ---------------------------------------------------------------

    async def report_llm_success(self) -> None:
        """上报 LLM API 调用成功"""
        await self._report("llm", True)

    async def report_llm_failure(self) -> None:
        """上报 LLM API 调用失败"""
        await self._report("llm", False)

    async def report_kg_success(self) -> None:
        await self._report("kg", True)

    async def report_kg_failure(self) -> None:
        await self._report("kg", False)

    async def report_mcp_success(self) -> None:
        await self._report("mcp", True)

    async def report_mcp_failure(self) -> None:
        await self._report("mcp", False)

    async def _report(self, component: str, success: bool) -> None:
        comp = self._components.get(component)
        if not comp:
            return

        comp.last_check = time.time()

        if success:
            if not comp.available and comp.fail_count < comp.max_fails:
                # 恢复中 —— 需要连续成功 max_fails 次
                comp.fail_count = max(0, comp.fail_count - 1)
                if comp.fail_count == 0:
                    comp.available = True
                    logger.info("Component '%s' recovered", comp.name)
            else:
                comp.fail_count = 0
                comp.available = True
        else:
            comp.fail_count += 1
            if comp.fail_count >= comp.max_fails and comp.available:
                comp.available = False
                logger.warning("Component '%s' marked UNAVAILABLE after %d failures",
                               comp.name, comp.fail_count)

        await self._recompute()

    # ---------------------------------------------------------------
    # 主动健康探测
    # ---------------------------------------------------------------

    async def probe_llm(self, probe_func: callable) -> bool:
        """探测 LLM 可用性（由调用方提供探测函数）"""
        try:
            result = await probe_func()
            await self.report_llm_success()
            return True
        except Exception as exc:
            logger.debug("LLM probe failed: %s", exc)
            await self.report_llm_failure()
            return False

    async def probe_kg(self, kg_instance) -> bool:
        """探测 KG 可用性"""
        try:
            available = kg_instance.is_loaded
            if available:
                await self.report_kg_success()
            else:
                await self.report_kg_failure()
            return available
        except Exception as exc:
            logger.debug("KG probe failed: %s", exc)
            await self.report_kg_failure()
            return False

    async def probe_mcp(self, tool_registry) -> bool:
        """探测 MCP Server 可用性"""
        try:
            alive = await tool_registry.health_check()
            if alive:
                await self.report_mcp_success()
            else:
                await self.report_mcp_failure()
            return alive
        except Exception as exc:
            logger.debug("MCP probe failed: %s", exc)
            await self.report_mcp_failure()
            return False

    # ---------------------------------------------------------------
    # 降级决策
    # ---------------------------------------------------------------

    async def _recompute(self) -> None:
        """根据各组件可用性重新计算降级级别"""
        async with self._lock:
            s = self._state
            llm_ok = self._components["llm"].available
            kg_ok = self._components["kg"].available
            mcp_ok = self._components["mcp"].available

            s.llm_available = llm_ok
            s.kg_available = kg_ok
            s.mcp_available = mcp_ok

            old_level = s.level

            if llm_ok and kg_ok and mcp_ok:
                s.level = FallbackLevel.FULL.value
            elif llm_ok and mcp_ok:
                s.level = FallbackLevel.LLM_ONLY.value
            elif mcp_ok:
                s.level = FallbackLevel.RULE_FALLBACK.value
            else:
                s.level = FallbackLevel.OFFLINE.value

            if s.level != old_level:
                logger.warning(
                    "StateMachine LEVEL CHANGE: %s → %s "
                    "(LLM=%s, KG=%s, MCP=%s)",
                    old_level, s.level, llm_ok, kg_ok, mcp_ok,
                )
                self._last_level = old_level
                await self._notify_level_change(old_level, s.level)

    async def evaluate(self) -> SystemState:
        """评估并返回当前系统状态"""
        await self._recompute()
        return self._state

    # ---------------------------------------------------------------
    # 降级模式信息
    # ---------------------------------------------------------------

    def get_mode_description(self) -> str:
        """返回当前降级模式的用户友好描述"""
        descriptions = {
            FallbackLevel.FULL.value: "全功能模式 — 知识图谱 + AI 推理 + 工具调用",
            FallbackLevel.LLM_ONLY.value: "降级模式 — 知识图谱不可用，使用 AI 内建知识回答（无知识溯源）",
            FallbackLevel.RULE_FALLBACK.value: "安全模式 — AI 不可用，使用本地规则引擎检查药物（仅覆盖关键高危相互作用）",
            FallbackLevel.OFFLINE.value: "离线模式 — 所有外部服务不可用，使用本地静态数据库（信息可能不完整）",
        }
        return descriptions.get(self._state.level, "未知模式")

    def get_mode_icon(self) -> str:
        icons = {
            FallbackLevel.FULL.value: "🟢",
            FallbackLevel.LLM_ONLY.value: "🟡",
            FallbackLevel.RULE_FALLBACK.value: "🟠",
            FallbackLevel.OFFLINE.value: "🔴",
        }
        return icons.get(self._state.level, "⚪")


# ============================================================
# 模块级单例
# ============================================================

state_machine = StateMachine()
