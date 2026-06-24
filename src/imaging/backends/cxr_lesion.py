"""MIMIC CXR pathology lesion segmentation — torchxrayvision pretrained DenseNet121."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np

from src.config import get_config
from src.imaging.backends.base import BaseSegmentBackend, SegmentResult
from src.imaging.cxr_lesion_runner import CXR_LESION_MAP, run_cxr_lesion_mask
from src.imaging.memory_monitor import memory_delta, release_torch, snapshot
from src.imaging.volume_io import is_visual_image, load_grayscale_array, save_overlay
from src.logging_config import get_logger

logger = get_logger("imaging.cxr_lesion")


class CXRLesionBackend(BaseSegmentBackend):
    model_id = "cxr_lesion"

    def is_available(self) -> bool:
        from src.imaging.cxr_lesion_runner import unet_weights_present
        if unet_weights_present():
            return True
        try:
            import torchxrayvision  # noqa: F401
            return True
        except ImportError:
            return False

    def unload(self) -> None:
        release_torch()

    def segment(self, image_path: str | Path, **kwargs: Any) -> SegmentResult:
        image_path = Path(image_path)
        if not is_visual_image(image_path):
            raise ValueError("cxr_lesion requires a 2D chest X-ray image (PNG/JPG)")

        lesion = kwargs.get("lesion") or kwargs.get("organ") or "opacity"
        device = str(kwargs.get("device") or get_config().get("imaging", {}).get("device", "cpu"))

        t0 = time.perf_counter()
        mem_before = snapshot("cxr_lesion_before", lesion=lesion)

        mask, meta = run_cxr_lesion_mask(image_path, lesion=lesion, device=device)
        arr = load_grayscale_array(image_path)
        if mask.shape != arr.shape[:2]:
            from PIL import Image
            mask = np.asarray(
                Image.fromarray((mask * 255).astype(np.uint8)).resize(
                    (arr.shape[1], arr.shape[0]), Image.NEAREST
                )
            ) > 127

        overlay = save_overlay(image_path, mask, color=(255, 87, 34))
        mem_after = snapshot("cxr_lesion_after")
        self.unload()

        return SegmentResult(
            model_id=self.model_id,
            source_image=str(image_path),
            overlay_path=str(overlay),
            labels=[meta["target_label"]],
            stats={
                **meta,
                "lesion_type": lesion,
                "mask_pixels": int(mask.sum()),
                "segmentation_method": meta.get("segmentation_method", "unknown"),
                "pretrained_on": meta.get("pretrained_on", ""),
                "supported_lesions": list(CXR_LESION_MAP.keys()),
            },
            memory_mb=memory_delta(mem_before, mem_after),
            duration_ms=(time.perf_counter() - t0) * 1000,
            notes=(
                f"CXR lesion: {meta['target_label']} "
                f"({meta.get('segmentation_method', 'segmentation')})"
            ),
        )
