#!/usr/bin/env python3
"""Pre-generate full imaging pipeline cache: VLM + rule review + multi-agent + report."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_config, resolve_path
from src.imaging.analysis_cache import ImagingAnalysisCacheStore
from src.imaging.catalog import ImagingCatalog
from src.imaging.report_cache import ImagingReportCacheStore
from src.imaging.warm_report import warm_study_full_report
from src.llm.errors import LLMNotConfiguredError


def clear_caches() -> None:
    for rel in ("data/imaging_cache/analysis", "data/imaging_cache/reports"):
        path = resolve_path(rel)
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)
    print(f"Cleared {resolve_path('data/imaging_cache/analysis')} and reports/")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Warm full imaging cache (VLM + multi-agent med review + saved report)",
    )
    parser.add_argument("--source", default="", help="Limit to one imaging source (mimic_cxr, brats2024, …)")
    parser.add_argument("--limit", type=int, default=0, help="Max studies to process (0 = all)")
    parser.add_argument("--force", action="store_true", help="Re-run even if full report cache exists")
    parser.add_argument("--clear", action="store_true", help="Delete analysis + report cache before running")
    parser.add_argument(
        "--vlm-only",
        action="store_true",
        help="Legacy: only Qwen VLM (+ optional DeepSeek), skip multi-agent report",
    )
    parser.add_argument("--skip-deepseek", action="store_true", help="With --vlm-only: skip DeepSeek synthesis")
    parser.add_argument("--dry-run", action="store_true", help="List studies only")
    args = parser.parse_args()

    if args.clear:
        clear_caches()

    load_config()
    catalog = ImagingCatalog()
    studies = catalog.list_studies(source=args.source or None)
    if args.limit > 0:
        studies = studies[: args.limit]

    if args.dry_run:
        for s in studies:
            print(f"{s.source}\t{s.patient_id}\t{s.study_id}\t{len(s.image_paths)} images")
        print(f"Total: {len(studies)}")
        return

    if args.vlm_only:
        from src.imaging.warm_analysis import warm_study_analysis

        store = ImagingAnalysisCacheStore()
        ok = skip = fail = 0
        for i, study in enumerate(studies, start=1):
            prefix = f"[{i}/{len(studies)}] {study.source}/{study.patient_id}/{study.study_id}"
            if not args.force and store.get(study.source, study.patient_id, study.study_id):
                print(f"{prefix} skip (vlm cached)")
                skip += 1
                continue
            try:
                warm_study_analysis(
                    study,
                    clinical_text=study.report_text or "",
                    force=args.force,
                    include_deepseek=not args.skip_deepseek,
                )
                print(f"{prefix} OK (vlm-only)")
                ok += 1
            except LLMNotConfiguredError as exc:
                print(f"{prefix} FAIL: {exc}")
                fail += 1
                break
            except Exception as exc:
                print(f"{prefix} FAIL: {exc}")
                fail += 1
        print(f"\nDone. warmed={ok}, skipped={skip}, failed={fail}, cache_dir={store.base_dir}")
        return

    analysis_store = ImagingAnalysisCacheStore()
    report_store = ImagingReportCacheStore()
    ok = skip = fail = 0
    for i, study in enumerate(studies, start=1):
        prefix = f"[{i}/{len(studies)}] {study.source}/{study.patient_id}/{study.study_id}"
        if not args.force:
            cached = report_store.get(study.source, study.patient_id, study.study_id)
            if cached and cached.metadata.get("medication_review_ran"):
                print(f"{prefix} skip (full report cached)")
                skip += 1
                continue
        try:
            _, report, from_cache = warm_study_full_report(study, force=args.force)
            if from_cache:
                print(f"{prefix} skip (full report cached)")
                skip += 1
            else:
                med = report.metadata.get("medication_review_ran") if report else False
                err = report.metadata.get("medication_review_error") if report else None
                if err:
                    print(f"{prefix} PARTIAL (med review error: {err})")
                elif med:
                    print(f"{prefix} OK (full pipeline)")
                else:
                    print(f"{prefix} OK (report saved, med review skipped — no candidate drugs?)")
                ok += 1
        except LLMNotConfiguredError as exc:
            print(f"{prefix} FAIL: {exc}")
            fail += 1
            break
        except Exception as exc:
            print(f"{prefix} FAIL: {exc}")
            fail += 1

    print(
        f"\nDone. warmed={ok}, skipped={skip}, failed={fail}, "
        f"analysis_dir={analysis_store.base_dir}, report_dir={report_store.base_dir}",
    )


if __name__ == "__main__":
    main()
