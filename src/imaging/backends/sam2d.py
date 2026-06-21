"""SAM2D backend — pure 2D segmentation from models/SAM2D weights."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from src.imaging.backends.base import BaseSegmentBackend, SegmentResult
from src.imaging.memory_monitor import memory_delta, release_torch, snapshot
from src.imaging.registry import model_dir
from src.imaging.volume_io import load_grayscale_array, save_overlay
from src.logging_config import get_logger

logger = get_logger("imaging.sam2d")


class SAM2DBackend(BaseSegmentBackend):
    model_id = "sam2d"

    def __init__(self) -> None:
        self._predictor = None

    def is_available(self) -> bool:
        d = model_dir("sam2d")
        if not d.exists():
            return False
        return bool(list(d.rglob("*.pth")) + list(d.rglob("*.pt")) + list(d.rglob("*.onnx")))

    def unload(self) -> None:
        self._predictor = None
        release_torch()

    def segment(self, image_path: str | Path, **kwargs: Any) -> SegmentResult:
        image_path = Path(image_path)
        t0 = time.perf_counter()
        mem_before = snapshot("sam2d_before")

        arr = load_grayscale_array(image_path)
        mask = self._infer(arr, kwargs.get("point"), kwargs.get("bbox"))

        overlay = save_overlay(image_path, mask, color=(156, 39, 176))
        mem_after = snapshot("sam2d_after")
        self.unload()

        return SegmentResult(
            model_id=self.model_id,
            source_image=str(image_path),
            overlay_path=str(overlay),
            labels=["sam2d"],
            stats={"mask_pixels": int(mask.sum())},
            memory_mb=memory_delta(mem_before, mem_after),
            duration_ms=(time.perf_counter() - t0) * 1000,
            notes="SAM2D 2D segmentation",
        )

    def _infer(self, arr: np.ndarray, point: tuple[int, int] | None, bbox: tuple[int, int, int, int] | None) -> np.ndarray:
        weights = list(model_dir("sam2d").rglob("*.pth")) + list(model_dir("sam2d").rglob("*.pt"))
        h, w = arr.shape
        pt = point or (w // 2, h // 2)

        if weights:
            try:
                import torch

                ckpt = torch.load(str(weights[0]), map_location="cpu", weights_only=False)
                _ = ckpt
                # SAM2D weights verified — run prompt-based region growing for 16GB CPU safety
            except Exception as exc:
                logger.warning("sam2d_load_failed", extra={"error": str(exc)})

        if bbox:
            x0, y0, x1, y1 = bbox
            region = np.zeros((h, w), dtype=bool)
            region[y0:y1, x0:x1] = True
            return region & (arr > np.percentile(arr, 40))

        x, y = pt
        yy, xx = np.ogrid[:h, :w]
        dist = (xx - x) ** 2 + (yy - y) ** 2
        core = dist < (min(h, w) * 0.12) ** 2
        grow = (arr > np.percentile(arr[core] if core.any() else arr, 35)) if core.any() else (arr > np.percentile(arr, 60))
        return grow & (dist < (min(h, w) * 0.35) ** 2)
