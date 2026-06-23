#!/usr/bin/env python3
"""Build studies_manifest.json for data/mimic_cxr/ (NLMCXR reports + image index)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.imaging.cxr_manifest import build_manifest, save_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build MIMIC-CXR / NLMCXR study manifest")
    parser.add_argument("--force-reports", action="store_true", help="Re-extract NLMCXR_reports.tgz")
    args = parser.parse_args()

    data = build_manifest(force_reports=args.force_reports)
    out = save_manifest(data)
    with_reports = sum(1 for s in data["studies"].values() if s.get("report_text"))
    print(f"Wrote {data['study_count']} studies -> {out.relative_to(ROOT)}")
    print(f"  with radiology reports: {with_reports}")


if __name__ == "__main__":
    main()
