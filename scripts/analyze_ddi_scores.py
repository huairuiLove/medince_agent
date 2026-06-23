#!/usr/bin/env python3
"""Analyze mined DDI score distribution and suggest thresholds."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze mined_ddi_scores.jsonl")
    parser.add_argument(
        "--scores",
        default="datasets/knowledge/mined_ddi_scores.jsonl",
        help="Path to scores JSONL",
    )
    parser.add_argument("--top", type=int, default=20, help="Show top-N pairs")
    args = parser.parse_args()

    path = PROJECT_ROOT / args.scores
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    rows: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    if not rows:
        print("No scores found.")
        sys.exit(0)

    probs = sorted(row["positive_prob"] for row in rows)
    n = len(probs)
    print(f"Total positive scores: {n}")
    print(f"  min={probs[0]:.3f}  median={probs[n // 2]:.3f}  max={probs[-1]:.3f}")
    print("\nThreshold sweep:")
    for threshold in [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]:
        count = sum(1 for p in probs if p >= threshold)
        print(f"  >={threshold:.2f}: {count:5d} rules ({count / n * 100:.1f}%)")

    rows.sort(key=lambda r: -r["positive_prob"])
    print(f"\nTop {args.top} pairs:")
    for row in rows[:args.top]:
        print(
            f"  {row['positive_prob']:.3f}  {row['drug_a']} + {row['drug_b']}"
            f"  [{row['risk_level']}]"
        )

    # Suggest thresholds
    high_cut = 0.70
    while high_cut >= 0.55 and sum(1 for p in probs if p >= high_cut) < 10:
        high_cut -= 0.02
    med_cut = 0.65
    print("\nSuggested mining thresholds (balance coverage vs noise):")
    print(f"  high_threshold:   {high_cut:.2f}  -> {sum(1 for p in probs if p >= high_cut)} rules")
    print(f"  medium_threshold: {med_cut:.2f}  -> {sum(1 for p in probs if p >= med_cut)} rules")


if __name__ == "__main__":
    main()
