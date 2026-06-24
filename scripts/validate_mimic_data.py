#!/usr/bin/env python3
"""Validate MIMIC-III raw tables and processed patient contexts for MedSafe."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.mimic_io import resolve_table_path, table_exists
from src.mimic_store import MimicStore

_RAW_TABLE_BASES = (
    "PATIENTS.csv",
    "ADMISSIONS.csv",
    "PRESCRIPTIONS.csv",
    "DIAGNOSES_ICD.csv",
    "D_ICD_DIAGNOSES.csv",
    "NOTEEVENTS.csv",
    "LABEVENTS.csv",
    "ICUSTAYS.csv",
)

FULL_MIMIC_PRESCRIPTION_BYTES = 50_000_000


def _count_csv_rows(path: Path) -> int | None:
    if not path.is_file():
        return None
    with path.open("rb") as handle:
        return sum(1 for _ in handle) - 1


def validate(*, strict: bool = False) -> int:
    store = MimicStore()
    raw_dir = store.raw_dir()
    issues: list[str] = []
    ok_lines: list[str] = []

    print(f"MIMIC-III raw dir: {raw_dir}")
    if not raw_dir.is_dir():
        issues.append(f"raw_dir missing: {raw_dir}")
    else:
        for table in _RAW_TABLE_BASES:
            path = resolve_table_path(raw_dir, table)
            if path is None:
                issues.append(f"missing table: {table}")
                continue
            size_mb = path.stat().st_size / (1024 * 1024)
            rows = _count_csv_rows(path)
            ok_lines.append(f"  OK {path.name}: {rows:,} rows, {size_mb:.1f} MB")

        all_csv = sorted(p.name for p in raw_dir.glob("*.csv"))
        all_gz = sorted(p.name for p in raw_dir.glob("*.csv.gz"))
        ok_lines.append(f"  total CSV tables: {len(all_csv)} (+ {len(all_gz)} gzipped)")

        rx = resolve_table_path(raw_dir, "PRESCRIPTIONS.csv")
        if rx is not None:
            if rx.stat().st_size >= FULL_MIMIC_PRESCRIPTION_BYTES:
                ok_lines.append("  dataset tier: full MIMIC-III 1.4")
            else:
                ok_lines.append("  dataset tier: demo / partial (<50MB prescriptions)")

    print("\nRaw tables:")
    if ok_lines:
        print("\n".join(ok_lines))
    if issues:
        print("\nRaw issues:")
        for item in issues:
            print(f"  FAIL {item}")

    processed = store.contexts_path()
    print(f"\nProcessed contexts: {processed}")
    if store.is_processed_available():
        stats = store.stats()
        print(f"  OK {stats.context_count} patient contexts")
        print(f"  with clinical notes: {stats.with_clinical_notes}")
        print(f"  with medications: {stats.with_medications}")
        print(f"  with diagnoses: {stats.with_diagnoses}")
        print(f"  with labs: {stats.with_labs}")
        print(f"  with ICU: {stats.with_icu}")
        print(f"  with imaging: {stats.with_imaging}")
        print(f"  dataset tier: {stats.dataset_tier}")
        if stats.age_min is not None:
            print(f"  age range: {stats.age_min}~{stats.age_max}")
        if stats.context_count == 0:
            issues.append("processed file empty")
        if strict and stats.with_clinical_notes == 0:
            if table_exists(raw_dir, "NOTEEVENTS.csv"):
                issues.append("full NOTEEVENTS present but contexts lack chief_complaint — rebuild with notes")
    else:
        issues.append(f"processed contexts missing: run `python -m src.cli build-mimic`")
        print("  FAIL not built yet")

    print("\nChest X-ray (datasets/mimic_cxr/):")
    cxr_issues, cxr_ok = _validate_cxr()
    issues.extend(cxr_issues)
    if cxr_ok:
        print("\n".join(cxr_ok))

    print("\n=== Summary ===")
    if issues:
        print(f"  status: INCOMPLETE ({len(issues)} issue(s))")
        for item in issues:
            print(f"    - {item}")
        return 1
    print("  status: OK")
    return 0


def _validate_cxr() -> tuple[list[str], list[str]]:
    from src.imaging.catalog import ImagingCatalog
    from src.imaging.cxr_manifest import manifest_path

    issues: list[str] = []
    ok_lines: list[str] = []
    catalog = ImagingCatalog()
    cxr = catalog.list_studies(source="mimic_cxr")
    png_count = sum(len(s.image_paths) for s in cxr)
    with_reports = sum(1 for s in cxr if s.report_text.strip())
    official = sum(1 for s in cxr if s.collection == "MIMIC-CXR-JPG")
    nlmcxr = sum(1 for s in cxr if s.collection == "NLMCXR")
    ok_lines.append(f"  CXR studies: {len(cxr)} ({png_count} images)")
    ok_lines.append(f"  MIMIC-CXR-JPG (datasets/mimic/): {official} studies")
    ok_lines.append(f"  NLMCXR (datasets/mimic_cxr/): {nlmcxr} studies")
    ok_lines.append(f"  with radiology reports: {with_reports}")
    manifest = manifest_path()
    if cxr and not manifest.is_file():
        issues.append("mimic_cxr present but studies_manifest.json missing — run scripts/build_mimic_cxr_manifest.py")
    elif manifest.is_file():
        ok_lines.append(f"  manifest: {manifest.relative_to(ROOT)}")
    if not cxr:
        issues.append("no CXR studies under datasets/mimic_cxr/")
    return issues, ok_lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate MIMIC-III data integration")
    parser.add_argument("--strict", action="store_true", help="Require clinical notes in processed contexts")
    args = parser.parse_args()
    sys.exit(validate(strict=args.strict))


if __name__ == "__main__":
    main()
