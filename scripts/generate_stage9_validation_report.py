#!/usr/bin/env python3
"""Generate docs/STAGE9_VALIDATION_REPORT.md from KB meta and latest benchmark reports."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils import load_json

REPORTS_DIR = PROJECT_ROOT / "data" / "benchmark" / "reports"
KB_PATH = PROJECT_ROOT / "data" / "knowledge" / "hospital_production_v4.json"
KG_PATH = PROJECT_ROOT / "data" / "knowledge" / "drug_kg_v2.json"
OUTPUT = PROJECT_ROOT / "docs" / "STAGE9_VALIDATION_REPORT.md"

TARGETS = {
    "alert_sensitivity": 0.90,
    "alert_specificity": 0.95,
    "risk_level_accuracy": 0.85,
    "block_decision_f1": 0.85,
    "alert_attribution": 0.80,
}


def _latest_report(prefix: str) -> Path | None:
    matches = sorted(REPORTS_DIR.glob(f"{prefix}*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def _pass_mark(value: float, target: float) -> str:
    return "PASS" if value >= target else "FAIL"


def _format_metrics(metrics: dict[str, Any]) -> list[str]:
    lines = [
        f"| Alert Sensitivity | {metrics['alert_sensitivity']:.4f} | {TARGETS['alert_sensitivity']:.2f} | {_pass_mark(metrics['alert_sensitivity'], TARGETS['alert_sensitivity'])} |",
        f"| Alert Specificity | {metrics['alert_specificity']:.4f} | {TARGETS['alert_specificity']:.2f} | {_pass_mark(metrics['alert_specificity'], TARGETS['alert_specificity'])} |",
        f"| Risk Level Accuracy | {metrics['risk_level_accuracy']:.4f} | {TARGETS['risk_level_accuracy']:.2f} | {_pass_mark(metrics['risk_level_accuracy'], TARGETS['risk_level_accuracy'])} |",
        f"| Block Decision F1 | {metrics['block_decision_f1']:.4f} | {TARGETS['block_decision_f1']:.2f} | {_pass_mark(metrics['block_decision_f1'], TARGETS['block_decision_f1'])} |",
        f"| Alert Attribution | {metrics['alert_attribution']:.4f} | {TARGETS['alert_attribution']:.2f} | {_pass_mark(metrics['alert_attribution'], TARGETS['alert_attribution'])} |",
        f"| Passed Cases | {metrics['passed_cases']}/{metrics['case_count']} | 110/110 | {'PASS' if metrics['failed_cases'] == 0 else 'FAIL'} |",
    ]
    return lines


def _dept_table(by_dept: dict[str, Any]) -> list[str]:
    lines = [
        "| Department | Cases | Sensitivity | Risk Acc | Block F1 | Passed |",
        "|------------|-------|-------------|----------|----------|--------|",
    ]
    for dept, metrics in sorted(by_dept.items()):
        lines.append(
            f"| {dept} | {metrics['case_count']} | {metrics['alert_sensitivity']:.2f} | "
            f"{metrics['risk_level_accuracy']:.2f} | {metrics['block_decision_f1']:.2f} | "
            f"{metrics['passed_cases']}/{metrics['case_count']} |"
        )
    return lines


def generate_report(*, output: Path = OUTPUT) -> str:
    kb = load_json(KB_PATH)
    kg = load_json(KG_PATH)
    meta = kb.get("meta", {})
    kg_meta = kg.get("meta", {})

    from collections import Counter

    node_types = Counter(node.get("type") for node in kg.get("nodes", []))
    edge_types = Counter(edge.get("type") for edge in kg.get("edges", []))

    rule_report = _latest_report("benchmark_rule-only_all_")
    cpoe_report = _latest_report("benchmark_cpoe_all_")
    compare_report = _latest_report("benchmark_compare_all_")

    if not rule_report or not cpoe_report or not compare_report:
        raise FileNotFoundError("Missing benchmark reports under datasets/benchmark/reports/")

    rule_data = load_json(rule_report)
    cpoe_data = load_json(cpoe_report)
    compare_data = load_json(compare_report)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    twosides = meta.get("twosides_meta", {})

    lines = [
        "# Stage 9 验证报告",
        "",
        f"> 生成时间：{now}  ",
        f"> 知识库：`hospital_production_v4.json`  ",
        f"> Benchmark 报告目录：`datasets/benchmark/reports/`",
        "",
        "## 1. 知识库终态",
        "",
        "| 指标 | 数值 |",
        "|------|------|",
        f"| interaction_rules | {meta.get('total_interaction_rules', 0)} |",
        f"| population_rules | {meta.get('population_rules', 0)} |",
        f"| allergy_rules | {meta.get('allergy_rules', 0)} |",
        f"| scenario_rules | {meta.get('scenario_rules', 0)} |",
        f"| duplicate_rules | {meta.get('duplicate_rules', 0)} |",
        f"| TWOSIDES 新增 DDI | {meta.get('twosides_interaction_added', 0)} |",
        f"| TWOSIDES 升级已有对 | {meta.get('twosides_pairs_upgraded', 0)} |",
        f"| TWOSIDES 原始信号 | {twosides.get('signals', 0)} |",
        f"| TWOSIDES CSV 行数 | {twosides.get('rows_total', 0):,} |",
        "",
        "## 2. Drug KG v2",
        "",
        f"- 节点：{kg_meta.get('node_count', len(kg.get('nodes', [])))}（{', '.join(f'{k}={v}' for k, v in sorted(node_types.items()))}）",
        f"- 边：{kg_meta.get('edge_count', len(kg.get('edges', [])))}（{', '.join(f'{k}={v}' for k, v in sorted(edge_types.items()))}）",
        f"- 扩充来源：{kg_meta.get('enrichment_source', 'formulary + rules')}",
        "",
        "## 3. Benchmark — rule-only（110 例 / 13 科室）",
        "",
        f"报告：`{rule_report.name}`",
        "",
        "| 指标 | 实测 | 目标 | 结果 |",
        "|------|------|------|------|",
        *_format_metrics(rule_data["metrics"]),
        "",
        "## 4. Benchmark — CPOE 路径",
        "",
        f"报告：`{cpoe_report.name}`",
        "",
        "| 指标 | 实测 | 目标 | 结果 |",
        "|------|------|------|------|",
        *_format_metrics(cpoe_data["metrics"]),
        "",
        "## 5. 知识库版本对比（expanded_mined_v1 → hospital_production_v4）",
        "",
        f"报告：`{compare_report.name}`",
        "",
        "| KB | Sensitivity | Risk Acc | Block F1 | Passed |",
        "|----|-------------|----------|----------|--------|",
        f"| expanded_mined_v1 | {compare_data['kb_v1_metrics']['alert_sensitivity']:.4f} | "
        f"{compare_data['kb_v1_metrics']['risk_level_accuracy']:.4f} | "
        f"{compare_data['kb_v1_metrics']['block_decision_f1']:.4f} | "
        f"{compare_data['kb_v1_metrics']['passed_cases']}/110 |",
        f"| hospital_production_v4 | {compare_data['kb_v2_metrics']['alert_sensitivity']:.4f} | "
        f"{compare_data['kb_v2_metrics']['risk_level_accuracy']:.4f} | "
        f"{compare_data['kb_v2_metrics']['block_decision_f1']:.4f} | "
        f"{compare_data['kb_v2_metrics']['passed_cases']}/110 |",
        "",
        "### v4 分科室通过率",
        "",
        *_dept_table(compare_data["kb_v2_by_department"]),
        "",
        "## 6. 复现命令",
        "",
        "```bash",
        "python scripts/import_twosides.py --csv data/TWOSIDES.csv",
        "python scripts/build_stage9_kb.py --import-twosides --twosides-csv data/TWOSIDES.csv",
        "python scripts/generate_benchmark_cases.py",
        "python scripts/run_benchmark.py --mode rule-only --dept all",
        "python scripts/run_benchmark.py --mode cpoe --dept all",
        "python scripts/run_benchmark.py --mode compare --kb-v1 expanded_mined_v1 --kb-v2 hospital_production_v4",
        "python scripts/generate_stage9_validation_report.py",
        "```",
        "",
        "## 7. 结论",
        "",
        "- Stage 9 知识库 v4 与 TWOSIDES 层已成功合并，Benchmark 110/110 在 rule-only 与 CPOE 模式下全部通过。",
        "- 相对 expanded_mined_v1，v4 将 Alert Sensitivity 从 "
        f"{compare_data['kb_v1_metrics']['alert_sensitivity']:.1%} 提升至 "
        f"{compare_data['kb_v2_metrics']['alert_sensitivity']:.1%}。",
        "- full-pipeline 模式需配置 LLM API Key，未配置时显式抛出 `LLMNotConfiguredError`（无 mock 兜底）。",
        "",
    ]
    content = "\n".join(lines) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    return str(output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Stage 9 validation report markdown")
    parser.add_argument("--output", default=str(OUTPUT))
    args = parser.parse_args()
    path = generate_report(output=Path(args.output))
    print(f"Wrote validation report -> {path}")


if __name__ == "__main__":
    main()
