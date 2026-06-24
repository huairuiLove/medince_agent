#!/usr/bin/env python3
"""Enhance department specialist base.md with structured professional prompts."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import datasets_path

REGISTRY_PATH = datasets_path("agents/registry.yaml")
AGENTS_ROOT = datasets_path("agents")

BASE_TEMPLATE = """你是 {{department}} 专科医生，以本科室临床路径与指南参与多智能体用药安全会诊。

## 专科定位
{role}

## 审查范围
- 本科室常见适应证：{{common_indications}}
- 重点关注检验/监测：{{lab_context_defaults}}
- 优先规则类别：{{priority_categories}}

## 职责边界
- 仅审查专科场景、特殊人群与科室相关 rule_evidence
- **不要**重复 DDI/CYP、过敏、库存/formulary 审查（已由临床药师/过敏专员/库管负责）
- 无专科规则命中时 block_decision=false，risk_level 通常为 low

## 输出要求
- summary 使用专科术语，给出可操作的临床建议
- reasons 引用与本专科相关的证据与监测要点
- alternatives 优先推荐本科室常用、路径内替代方案
"""


def main() -> None:
    with REGISTRY_PATH.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    updated = 0
    for agent_id, entry in (raw.get("department_agents") or {}).items():
        role = entry.get("role", "专科用药安全审查")
        path = AGENTS_ROOT / agent_id / "base.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(BASE_TEMPLATE.replace("{role}", role).strip() + "\n", encoding="utf-8")
        updated += 1

    print(f"Updated {updated} department base.md files")


if __name__ == "__main__":
    main()
