"""BraTS glioma tumor lesion segmentation — MONAI brats_mri_segmentation pretrained weights."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from src.config import get_config, resolve_path
from src.imaging.backends.base import BaseSegmentBackend, SegmentResult
from src.imaging.brats_tumor_runner import run_brats_tumor_volume
from src.imaging.memory_monitor import memory_delta, release_torch, snapshot
from src.imaging.registry import model_dir
from src.imaging.volume_io import (
    VolumeAxis,
    export_volume_slice,
    is_nifti,
    save_overlay_from_mask_volume,
)
from src.logging_config import get_logger

logger = get_logger("imaging.brats_tumor")


class BraTSTumorBackend(BaseSegmentBackend):
    model_id = "brats_tumor"

    def is_available(self) -> bool:
        ckpt = model_dir("brats_tumor") / "models" / "model.pt"
        if not ckpt.exists():
            return False
        try:
            import monai  # noqa: F401
            return True
        except ImportError:
            return False

    def unload(self) -> None:
        release_torch()

    def segment(self, image_path: str | Path, **kwargs: Any) -> SegmentResult:
        image_path = Path(image_path)
        volume_path = kwargs.get("volume_path") or image_path
        vol = Path(volume_path)
        if not vol.is_absolute():
            vol = resolve_path(str(volume_path))
        volume_path = vol
        region = kwargs.get("organ") or kwargs.get("lesion") or "whole_tumor"
        axis: VolumeAxis = kwargs.get("slice_axis", "axial")
        slice_index = int(kwargs.get("slice_index", 0))
        device = get_config().get("imaging", {}).get("device", "cpu")

        t0 = time.perf_counter()
        mem_before = snapshot("brats_tumor_before", region=region)

        if not is_nifti(volume_path):
            raise ValueError("brats_tumor requires BraTS NIfTI volume_path with t1c/t1n/t2w/t2f")

        mask_path = run_brats_tumor_volume(volume_path, region=region, device=device)
        display = image_path if image_path.exists() else volume_path
        if is_nifti(display):
            overlay_png = export_volume_slice(
                volume_path,
                axis=axis,
                slice_index=slice_index,
                mask_path=mask_path,
                overlay_color=(220, 50, 50),
            )
            overlay_path = str(overlay_png)
        else:
            overlay_path = str(save_overlay_from_mask_volume(display, mask_path, axis, slice_index))

        mem_after = snapshot("brats_tumor_after")
        self.unload()

        return SegmentResult(
            model_id=self.model_id,
            source_image=str(display),
            overlay_path=overlay_path,
            mask_path=str(mask_path),
            labels=[region],
            stats={
                "volume_mask_path": str(mask_path),
                "tumor_region": region,
                "pretrained_on": "BraTS2018 (MONAI brats_mri_segmentation)",
            },
            memory_mb=memory_delta(mem_before, mem_after),
            duration_ms=(time.perf_counter() - t0) * 1000,
            notes=f"BraTS tumor {region} (ET/TC/WT pretrained)",
        )
