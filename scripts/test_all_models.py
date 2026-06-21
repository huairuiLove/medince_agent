"""Test all segmentation backends on MIMIC CT + BraTS MRI slices."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.imaging.catalog import ImagingCatalog
from src.imaging.memory_monitor import rss_mb
from src.imaging.registry import ModelId
from src.imaging.segment_service import SegmentService


def _status(r) -> tuple[str, str]:
    notes = (r.notes or "").lower()
    mask_px = int((r.stats or {}).get("mask_pixels", 0))
    if "failed:" in notes:
        return "FAIL", r.notes or ""
    if mask_px == 0:
        return "WARN", f"mask_px=0; {r.notes}"
    if "fallback" in notes or "heuristic" in notes:
        return "PARTIAL", f"mask_px={mask_px}; {r.notes}"
    return "PASS", f"mask_px={mask_px}; {r.notes}"


def main() -> int:
    catalog = ImagingCatalog()
    studies = catalog.list_studies()
    if not studies:
        print("No imaging studies found.")
        return 1

    mimic_img = brats_img = None
    for s in studies:
        if s.source == "mimic" and s.image_paths and not mimic_img:
            mimic_img = s.image_paths[0]
        if s.source == "brats2024" and s.image_paths and not brats_img:
            brats_img = s.image_paths[0]

    models: list[ModelId] = ["sam2d", "sam_med3d", "vista3d", "totalsegmentator"]
    service = SegmentService()
    peak = rss_mb()
    rows: list[tuple[str, str, str, float, str]] = []

    print(f"Baseline RSS: {rss_mb():.1f} MB")

    for label, img in [("mimic_ct", mimic_img), ("brats_mri", brats_img)]:
        if not img:
            print(f"\nSkip {label}: no image")
            continue
        print(f"\n=== {label}: {Path(img).name} ===")
        for model_id in models:
            print(f"  Running {model_id}...", flush=True)
            try:
                results = service.segment_serial(img, [model_id], organ="brain")
                r = results[0]
                peak = max(peak, rss_mb())
                status, detail = _status(r)
                rows.append((model_id, label, status, r.duration_ms, detail))
                print(f"  {model_id}: {status} ({r.duration_ms:.0f}ms) {detail}")
            except Exception as exc:
                rows.append((model_id, label, "FAIL", 0.0, str(exc)))
                print(f"  {model_id}: FAIL {exc}")

    print("\n" + "=" * 72)
    print(f"{'Model':<18} {'Dataset':<12} {'Status':<8} {'Time(ms)':<10} Detail")
    print("-" * 72)
    for model_id, label, status, ms, detail in rows:
        print(f"{model_id:<18} {label:<12} {status:<8} {ms:<10.0f} {detail[:45]}")
    print(f"\nPeak RSS: {peak:.1f} MB")

    fails = sum(1 for _, _, s, _, _ in rows if s == "FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
