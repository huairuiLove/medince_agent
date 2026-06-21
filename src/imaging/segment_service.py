"""Serial segmentation orchestrator — one model in memory at a time."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from src.imaging.backends.base import BaseSegmentBackend, SegmentResult
from src.imaging.backends.sam2d import SAM2DBackend
from src.imaging.backends.sam_med3d import SAMMed3DBackend
from src.imaging.backends.totalsegmentator import TotalSegmentatorBackend
from src.imaging.backends.vista3d import Vista3DBackend
from src.imaging.memory_monitor import release_torch, snapshot
from src.imaging.registry import MODEL_REGISTRY, ModelId
from src.logging_config import get_logger

logger = get_logger("imaging.segment_service")

BACKEND_MAP: dict[ModelId, type[BaseSegmentBackend]] = {
    "totalsegmentator": TotalSegmentatorBackend,
    "vista3d": Vista3DBackend,
    "sam_med3d": SAMMed3DBackend,
    "sam2d": SAM2DBackend,
}


class SegmentService:
    def __init__(self) -> None:
        self._active: BaseSegmentBackend | None = None

    def list_models(self) -> list[dict]:
        from src.imaging.registry import list_models
        return list_models()

    def _get_backend(self, model_id: ModelId) -> BaseSegmentBackend:
        if model_id not in BACKEND_MAP:
            raise ValueError(f"Unknown model: {model_id}")
        return BACKEND_MAP[model_id]()

    def _unload_active(self) -> None:
        if self._active:
            self._active.unload()
            self._active = None
        release_torch()

    def segment_serial(
        self,
        image_path: str | Path,
        model_ids: list[ModelId],
        **kwargs: Any,
    ) -> list[SegmentResult]:
        results: list[SegmentResult] = []
        snapshot("segment_serial_start", models=model_ids)

        for model_id in model_ids:
            if model_id not in MODEL_REGISTRY:
                continue
            self._unload_active()
            backend = self._get_backend(model_id)
            logger.info("segment_start", extra={"model_id": model_id, "image": str(image_path)})
            try:
                result = backend.segment(image_path, **kwargs)
                results.append(result)
            except Exception as exc:
                logger.error("segment_failed", extra={"model_id": model_id, "error": str(exc)})
                results.append(
                    SegmentResult(
                        model_id=model_id,
                        source_image=str(image_path),
                        overlay_path=str(image_path),
                        notes=f"failed: {exc}",
                    )
                )
            finally:
                backend.unload()
                self._unload_active()

        snapshot("segment_serial_end", count=len(results))
        return results
