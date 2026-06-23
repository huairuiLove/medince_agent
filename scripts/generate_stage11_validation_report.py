#!/usr/bin/env python3
"""Generate docs/STAGE11_VALIDATION_REPORT.md from KB meta and latest benchmark."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.knowledge_mining.stage11_department_rules import get_stage11_rules
from src.utils import load_json

REPORTS_DIR = PROJECT_ROOT / "datasets" / "benchmark" / "reports"
KB_PATH = PROJECT_ROOT / "datasets" / "knowledge" / "hospital_production_v5.json"
OUT_PATH = PROJECT_ROOT / "docs" / "STAGE11_VALIDATION_REPORT.md"
CASES_DIR = PROJECT_ROOT / "datasets" / "benchmark" / "cases"


def _latest_report(prefix: str) -> dict | None:
    matches = sorted(REPORTS_DIR.glob(f"{prefix}*.json"), reverse=True)
    return load_json(matches[0]) if matches else None


def main() -> None:
    kb = load_json(KB_PATH)
    meta = kb.get("meta", {})
    stage11 = get_stage11_rules()["meta"]
    clinical = len(list(CASES_DIR.glob("clinical_*.json")))
    negative = len(list(CASES_DIR.glob("negative_*.json")))
    report = _latest_report("benchmark_rule-only_all_")

    lines = [
        "# Stage 11 Validation Report",
        "",
        f"> Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Knowledge Base (hospital_production_v5)",
        "",
        f"- Total interaction rules: **{meta.get('total_interaction_rules', 0)}**",
        f"- Stage 11 department DDI rules: **{stage11.get('interaction_count', 0)}**",
        "",
        "## Benchmark Cases",
        "",
        f"- Stage 11 clinical cases: **{clinical}**",
        f"- Stage 11 negative tests: **{negative}**",
        f"- Total benchmark JSON files: **{len(list(CASES_DIR.glob('*.json')))}**",
        "",
    ]
    if report:
        m = report.get("metrics", {})
        boost = m.get("department_boost") or {}
        lines.extend(
            [
                "## Latest rule-only Benchmark",
                "",
                f"- Alert sensitivity: {m.get('alert_sensitivity')}",
                f"- Risk level accuracy: {m.get('risk_level_accuracy')}",
                f"- Department boost accuracy: {boost.get('department_boost_accuracy')}",
                f"- Failed cases: {m.get('failed_cases')}",
                "",
            ]
        )
    lines.extend(
        [
            "## Commands",
            "",
            "```bash",
            "python scripts/build_stage11_kb.py --without-twosides",
            "python scripts/generate_stage11_clinical_benchmark.py --auto-per-dept 4",
            "python scripts/run_benchmark.py --mode rule-only --dept all --kb hospital_production_v5",
            "```",
        ]
    )
    OUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
