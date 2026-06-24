"""TotalSegmentator backend — 2D slice / fast mode, serial load."""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from src.config import resolve_path
from src.imaging.backends.base import BaseSegmentBackend, SegmentResult
from src.imaging.memory_monitor import memory_delta, release_torch, snapshot
from src.imaging.registry import model_dir
from src.imaging.volume_io import save_overlay
from src.logging_config import get_logger

logger = get_logger("imaging.totalsegmentator")

ORGAN_ROI_SUBSET: dict[str, list[str]] = {
    "brain": ["brain"],
    "liver": ["liver"],
    "lung": [
        "lung_upper_lobe_left",
        "lung_lower_lobe_left",
        "lung_upper_lobe_right",
        "lung_middle_lobe_right",
        "lung_lower_lobe_right",
    ],
    "kidney": ["kidney_left", "kidney_right"],
}


class TotalSegmentatorBackend(BaseSegmentBackend):
    model_id = "totalsegmentator"

    def __init__(self) -> None:
        self._loaded = False

    def is_available(self) -> bool:
        try:
            import totalsegmentator  # noqa: F401
            return True
        except ImportError:
            return False

    def _ensure_home(self) -> None:
        home = model_dir("totalsegmentator")
        weights = home / "nnunet" / "results"
        weights.mkdir(parents=True, exist_ok=True)
        os.environ["TOTALSEG_WEIGHTS_PATH"] = str(weights)
        os.environ["TOTALSEG_HOME_DIR"] = str(home)

    def unload(self) -> None:
        self._loaded = False
        release_torch()

    def segment(self, image_path: str | Path, **kwargs: Any) -> SegmentResult:
        self._ensure_home()
        image_path = Path(image_path)
        t0 = time.perf_counter()
        mem_before = snapshot("totalseg_before")

        # Build 1-slice pseudo-volume NIfTI for 2D JPG inputs
        nii_input = self._to_nifti_if_needed(image_path)
        out_dir = resolve_path(f"data/imaging_cache/totalseg/{image_path.stem}")
        out_dir.mkdir(parents=True, exist_ok=True)

        fast = kwargs.get("fast", True)
        organ = str(kwargs.get("organ") or "").strip().lower()
        roi_subset = kwargs.get("roi_subset")
        if not roi_subset and organ in ORGAN_ROI_SUBSET:
            roi_subset = ORGAN_ROI_SUBSET[organ]
        if not roi_subset:
            roi_subset = ["liver", "lung", "brain"]

        try:
            from totalsegmentator.python_api import totalsegmentator as ts_predict
            if not callable(ts_predict):
                raise RuntimeError(
                    "TotalSegmentator API unavailable. Run: pip install 'totalsegmentator>=2.3.0'"
                )
            ts_predict(
                str(nii_input),
                str(out_dir),
                fast=fast,
                ml=True,
                roi_subset=roi_subset,
                nr_thr_resamp=1,
                nr_thr_saving=1,
                device="cpu",
                quiet=True,
            )
            mask = self._collect_mask(out_dir, image_path)
        except Exception as exc:
            logger.warning("totalseg_failed_fallback", extra={"error": str(exc)})
            mask = self._fallback_mask(image_path)

        overlay = save_overlay(image_path, mask, color=(0, 180, 120))
        mem_after = snapshot("totalseg_after")
        self.unload()

        return SegmentResult(
            model_id=self.model_id,
            source_image=str(image_path),
            overlay_path=str(overlay),
            labels=list(roi_subset),
            stats={"mask_pixels": int(mask.sum()), "mode": "2d_slice_fast"},
            memory_mb=memory_delta(mem_before, mem_after),
            duration_ms=(time.perf_counter() - t0) * 1000,
            notes="TotalSegmentator fast CPU 2D-slice mode",
        )

    def _to_nifti_if_needed(self, image_path: Path) -> Path:
        if image_path.suffix.lower() in {".nii", ".gz"} or str(image_path).endswith(".nii.gz"):
            return image_path
        try:
            import nibabel as nib
        except ImportError:
            return image_path

        arr = np.asarray(Image.open(image_path).convert("L"), dtype=np.float32)
        vol = arr[:, :, np.newaxis]
        out = resolve_path(f"data/imaging_cache/totalseg/{image_path.stem}_vol.nii.gz")
        out.parent.mkdir(parents=True, exist_ok=True)
        nib.save(nib.Nifti1Image(vol, np.eye(4)), str(out))
        return out

    def _collect_mask(self, out_dir: Path, image_path: Path) -> np.ndarray:
        masks = list(out_dir.rglob("*.nii.gz"))
        if not masks:
            return self._fallback_mask(image_path)
        try:
            import nibabel as nib
        except ImportError:
            return self._fallback_mask(image_path)

        base = np.asarray(Image.open(image_path).convert("L"))
        combined = np.zeros(base.shape, dtype=bool)
        for m in masks:
            data = nib.load(str(m)).get_fdata()
            slc = data[:, :, 0] if data.ndim == 3 else data
            if slc.shape != base.shape:
                slc = np.asarray(Image.fromarray(slc).resize((base.shape[1], base.shape[0]), Image.NEAREST))
            combined |= slc > 0
        return combined

    @staticmethod
    def _fallback_mask(image_path: Path) -> np.ndarray:
        arr = np.asarray(Image.open(image_path).convert("L"), dtype=np.float32)
        thresh = np.percentile(arr, 72)
        return arr > thresh
