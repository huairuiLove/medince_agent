"""Forward-pass memory test on visual images only."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.imaging.catalog import ImagingCatalog
from src.imaging.memory_monitor import rss_mb, snapshot
from src.imaging.registry import ModelId
from src.imaging.segment_service import SegmentService


def main():
    catalog = ImagingCatalog()
    studies = catalog.list_studies()
    if not studies:
        print("No imaging studies found.")
        return 1

    # Pick first mimic JPG study and first brats PNG study
    targets: list[tuple[str, str]] = []
    for s in studies:
        if s.source == "mimic" and s.image_paths:
            targets.append(("mimic_ct", s.image_paths[0]))
            break
    for s in studies:
        if s.source == "brats2024" and s.image_paths:
            targets.append(("brats_mri", s.image_paths[0]))
            break

    service = SegmentService()
    models: list[ModelId] = ["sam2d", "sam_med3d", "vista3d"]

    print(f"Baseline RSS: {rss_mb():.1f} MB")
    peak = rss_mb()

    for label, img in targets:
        print(f"\n=== {label}: {img} ===")
        for model_id in models:
            snap = snapshot(f"before_{model_id}")
            results = service.segment_serial(img, [model_id], organ="brain")
            after = rss_mb()
            peak = max(peak, after)
            r = results[0]
            print(
                f"  {model_id}: {r.duration_ms:.0f}ms, "
                f"mem_delta={r.memory_mb:.1f}MB, rss={after:.1f}MB, overlay={r.overlay_path}"
            )

    print(f"\nPeak RSS: {peak:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
