"""MONAI VISTA3D backend — real 3D volume + thin-stack 2D slice inference."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np

from src.imaging.backends.base import BaseSegmentBackend, SegmentResult
from src.imaging.memory_monitor import memory_delta, release_torch, snapshot
from src.imaging.registry import model_dir
from src.imaging.volume_io import (
    VolumeAxis,
    export_pseudo_nifti_from_image,
    export_volume_slice,
    is_nifti,
    is_visual_image,
    load_grayscale_array,
    save_overlay,
    save_overlay_from_mask_volume,
)
from src.imaging.vista3d_runner import run_vista3d_volume
from src.logging_config import get_logger

logger = get_logger("imaging.vista3d")


class Vista3DBackend(BaseSegmentBackend):
    model_id = "vista3d"

    def __init__(self) -> None:
        self._bundle = None

    def is_available(self) -> bool:
        bundle_dir = model_dir("vista3d")
        has_weights = any(bundle_dir.rglob("*.pt")) or any(bundle_dir.rglob("*.pth"))
        if not has_weights:
            return False
        try:
            import monai  # noqa: F401
            return True
        except ImportError:
            return False

    def unload(self) -> None:
        self._bundle = None
        release_torch()

    def segment(self, image_path: str | Path, **kwargs: Any) -> SegmentResult:
        image_path = Path(image_path)
        organ = kwargs.get("organ", "brain")
        volume_path = kwargs.get("volume_path")
        axis: VolumeAxis = kwargs.get("slice_axis", "axial")
        slice_index = int(kwargs.get("slice_index", 0))
        t0 = time.perf_counter()
        mem_before = snapshot("vista3d_before", organ=organ)

        if volume_path and Path(volume_path).exists() and is_nifti(volume_path):
            return self._segment_volume_3d(
                Path(volume_path), image_path, organ, axis, slice_index, t0, mem_before,
            )

        if is_nifti(image_path):
            return self._segment_volume_3d(
                image_path, image_path, organ, axis, slice_index, t0, mem_before,
            )

        if is_visual_image(image_path):
            pseudo_vol, mid_z = export_pseudo_nifti_from_image(image_path)
            return self._segment_volume_3d(
                pseudo_vol,
                image_path,
                organ,
                "axial",
                mid_z,
                t0,
                mem_before,
                mode_label="2d_via_3d",
            )

        arr = load_grayscale_array(image_path)
        mask = self._organ_heuristic(arr, organ)
        overlay = save_overlay(image_path, mask, color=(25, 118, 210))
        mem_after = snapshot("vista3d_after")
        self.unload()
        return SegmentResult(
            model_id=self.model_id,
            source_image=str(image_path),
            overlay_path=str(overlay),
            labels=[organ],
            stats={"mask_pixels": int(mask.sum()), "organ": organ, "mode": "heuristic"},
            memory_mb=memory_delta(mem_before, mem_after),
            duration_ms=(time.perf_counter() - t0) * 1000,
            notes=f"VISTA3D heuristic — {organ}",
        )

    def _segment_volume_3d(
        self,
        volume_path: Path,
        display_path: Path,
        organ: str,
        axis: VolumeAxis,
        slice_index: int,
        t0: float,
        mem_before: dict,
        mode_label: str = "3d_volume",
    ) -> SegmentResult:
        try:
            mask_path = run_vista3d_volume(volume_path, organ=organ, device="cpu")
            if is_visual_image(display_path):
                overlay = save_overlay_from_mask_volume(
                    display_path, mask_path, axis=axis, slice_index=slice_index,
                )
            else:
                overlay = export_volume_slice(
                    volume_path,
                    axis=axis,
                    slice_index=slice_index,
                    mask_path=mask_path,
                )
            import nibabel as nib
            mask_vol = nib.load(str(mask_path)).get_fdata()
            mask_px = int((mask_vol > 0).sum())
            notes = f"VISTA3D MONAI {mode_label} — {organ}"
            mode = mode_label
        except Exception as exc:
            logger.warning("vista3d_inference_failed", extra={"error": str(exc)})
            arr = load_grayscale_array(display_path)
            mask = self._organ_heuristic(arr, organ)
            overlay = save_overlay(display_path, mask, color=(25, 118, 210))
            mask_path = None
            mask_px = int(mask.sum())
            notes = f"VISTA3D failed, heuristic — {exc}"
            mode = "heuristic"

        mem_after = snapshot("vista3d_after")
        self.unload()

        stats: dict[str, Any] = {
            "mask_pixels": mask_px,
            "organ": organ,
            "mode": mode,
            "slice_axis": axis,
            "slice_index": slice_index,
        }
        if mask_path:
            stats["volume_mask_path"] = str(mask_path)

        return SegmentResult(
            model_id=self.model_id,
            source_image=str(display_path),
            overlay_path=str(overlay),
            labels=[organ],
            stats=stats,
            memory_mb=memory_delta(mem_before, mem_after),
            duration_ms=(time.perf_counter() - t0) * 1000,
            notes=notes,
        )

    @staticmethod
    def _organ_heuristic(arr: np.ndarray, organ: str) -> np.ndarray:
        h, w = arr.shape
        yy, xx = np.ogrid[:h, :w]
        cy, cx = h * 0.5, w * 0.5
        if organ == "brain":
            r = min(h, w) * 0.28
            return ((yy - cy) ** 2 + (xx - cx) ** 2) <= r ** 2
        if organ == "liver":
            return (xx > w * 0.45) & (xx < w * 0.85) & (yy > h * 0.35) & (yy < h * 0.78) & (arr > np.percentile(arr, 55))
        if organ == "lung":
            left = (xx < w * 0.48) & (arr > np.percentile(arr, 50))
            right = (xx > w * 0.52) & (arr > np.percentile(arr, 50))
            return left | right
        return arr > np.percentile(arr, 70)
