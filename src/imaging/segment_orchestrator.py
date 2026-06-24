"""Local/remote segmentation orchestration with fallback."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import HTTPException

from src.imaging.backends.base import SegmentResult
from src.imaging.memory_monitor import rss_mb
from src.imaging.remote_client import run_remote_segment
from src.imaging.remote_config import get_remote_segment_config, remote_segment_configured
from src.imaging.registry import ModelId
from src.logging_config import get_logger

logger = get_logger("imaging.segment_orchestrator")


def _local_segment_kwargs(kwargs: dict[str, Any], *, force_cpu: bool) -> dict[str, Any]:
    merged = dict(kwargs)
    if force_cpu:
        merged["device"] = get_remote_segment_config().get("local_fallback_device", "cpu")
    return merged


def segment_results_to_payload(results: list[SegmentResult]) -> list[dict[str, Any]]:
    return [{
        "model_id": r.model_id,
        "source_image": r.source_image,
        "overlay_path": r.overlay_path,
        "labels": r.labels,
        "stats": r.stats,
        "memory_mb": r.memory_mb,
        "duration_ms": r.duration_ms,
        "notes": r.notes,
    } for r in results]


def run_segment_with_fallback(
    *,
    segment_service: object,
    visual: str | Path,
    model_ids: list[ModelId],
    image_abs: Path,
    volume_abs: Path | None,
    kwargs: dict[str, Any],
    organ: str,
    slice_axis: str,
    slice_index: int | None,
    point: list[int] | None = None,
    bbox: list[int] | None = None,
) -> tuple[list[SegmentResult], float, str, str, bool]:
    """Return results, memory_peak_mb, compute_mode, compute_message, fallback_from_remote."""
    cfg = get_remote_segment_config()

    if remote_segment_configured():
        remote_out = run_remote_segment(
            model_ids=model_ids,
            image_path=image_abs,
            volume_path=volume_abs,
            organ=organ,
            slice_axis=slice_axis,
            slice_index=slice_index,
            point=point,
            bbox=bbox,
        )
        if remote_out.ok and remote_out.results is not None:
            logger.info(
                "segment_remote_ok",
                extra={"job_id": remote_out.job_id, "models": model_ids},
            )
            return (
                remote_out.results,
                remote_out.memory_peak_mb,
                "remote",
                "已使用云端 GPU 完成分割",
                False,
            )

        reason = remote_out.error or "云端分割服务不可用"
        logger.warning("segment_remote_failed", extra={"error": reason})
        if not cfg["fallback_to_local"]:
            raise HTTPException(
                status_code=503,
                detail=f"云端分割不可用且未启用本地降级：{reason}",
            )
        peak_before = rss_mb()
        local_results = segment_service.segment_serial(
            visual,
            model_ids,
            **_local_segment_kwargs(kwargs, force_cpu=True),
        )
        peak_after = rss_mb()
        return (
            local_results,
            max(peak_before, peak_after),
            "local",
            f"云端分割服务不可用，已降级为本地 CPU 运算：{reason}",
            True,
        )

    peak_before = rss_mb()
    local_results = segment_service.segment_serial(visual, model_ids, **kwargs)
    peak_after = rss_mb()
    return (
        local_results,
        max(peak_before, peak_after),
        "local",
        "",
        False,
    )
