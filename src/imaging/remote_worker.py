"""Remote GPU segment worker — run on AutoDL / cloud server."""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse

from src.config import load_config, resolve_path
from src.imaging.backends.base import SegmentResult
from src.imaging.memory_monitor import rss_mb
from src.imaging.remote_config import get_remote_segment_config
from src.imaging.registry import ModelId
from src.imaging.segment_service import SegmentService
from src.logging_config import get_logger, setup_logging
from src.utils import ensure_dir

logger = get_logger("imaging.remote_worker")

app = FastAPI(title="MedSafe Segment Worker", version="1.0.0")
_SEGMENT_SERVICE = SegmentService()
_JOBS_ROOT = resolve_path("data/imaging_cache/remote_jobs")


def _verify_token(authorization: str | None = None, x_api_token: str | None = None) -> None:
    cfg = get_remote_segment_config()
    expected = cfg["api_token"]
    if not expected:
        return
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    elif x_api_token:
        token = x_api_token.strip()
    if token != expected:
        raise HTTPException(status_code=401, detail="Invalid segment worker token")


def _auth_dep(
    authorization: Annotated[str | None, Header()] = None,
    x_api_token: Annotated[str | None, Header(alias="X-Api-Token")] = None,
) -> None:
    _verify_token(authorization=authorization, x_api_token=x_api_token)


AuthDep = Annotated[None, Depends(_auth_dep)]


def _result_payload(results: list[SegmentResult]) -> list[dict[str, Any]]:
    return [{
        "model_id": r.model_id,
        "source_image": r.source_image,
        "overlay_path": r.overlay_path,
        "mask_path": r.mask_path,
        "labels": r.labels,
        "stats": r.stats,
        "memory_mb": r.memory_mb,
        "duration_ms": r.duration_ms,
        "notes": r.notes,
    } for r in results]


def _stage_artifacts(results: list[dict[str, Any]], job_dir: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Copy backend outputs into job_dir/artifacts and rewrite result paths."""
    artifacts_dir = job_dir / "artifacts"
    ensure_dir(artifacts_dir)
    staged: list[str] = []

    def _stage(path_val: str | None, tag: str) -> str | None:
        if not path_val:
            return None
        source = Path(path_val).resolve()
        if not source.is_file():
            return path_val
        dest_name = f"{tag}_{source.name}"
        dest = artifacts_dir / dest_name
        if not dest.exists() or dest.stat().st_size != source.stat().st_size:
            shutil.copy2(source, dest)
        rel = dest.relative_to(job_dir.resolve()).as_posix()
        staged.append(rel)
        return rel

    rewritten: list[dict[str, Any]] = []
    for idx, item in enumerate(results):
        row = dict(item)
        row["source_image"] = _stage(row.get("source_image"), f"r{idx}_src") or row.get("source_image")
        row["overlay_path"] = _stage(row.get("overlay_path"), f"r{idx}_overlay") or row.get("overlay_path")
        if row.get("mask_path"):
            row["mask_path"] = _stage(row.get("mask_path"), f"r{idx}_mask")
        stats = dict(row.get("stats") or {})
        if stats.get("volume_mask_path"):
            stats["volume_mask_path"] = _stage(stats["volume_mask_path"], f"r{idx}_vmask")
        row["stats"] = stats
        rewritten.append(row)

    return rewritten, sorted(set(staged))


@app.on_event("startup")
def _startup() -> None:
    cfg = load_config()
    log_cfg = cfg.get("logging", {})
    setup_logging(
        level=log_cfg.get("level", "INFO"),
        log_format=log_cfg.get("format", "console"),
        log_dir=log_cfg.get("log_dir"),
        log_file="segment_worker.log",
    )
    ensure_dir(_JOBS_ROOT)
    logger.info("segment_worker_ready", extra={"jobs_root": str(_JOBS_ROOT)})


@app.get("/health")
def health(_: AuthDep) -> dict[str, Any]:
    from src.config import get_config

    imaging = get_config().get("imaging", {}) or {}
    return {
        "status": "ok",
        "service": "medsafe_segment_worker",
        "device": imaging.get("device", "cpu"),
        "models": _SEGMENT_SERVICE.list_models(),
    }


@app.post("/internal/segment")
async def run_remote_segment(
    _: AuthDep,
    metadata: str = Form(...),
    image: UploadFile = File(...),
    volume: UploadFile | None = File(None),
) -> dict[str, Any]:
    try:
        meta = json.loads(metadata)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid metadata JSON: {exc}") from exc

    model_ids: list[ModelId] = list(meta.get("model_ids") or [])
    if not model_ids:
        raise HTTPException(status_code=400, detail="model_ids required")

    job_id = uuid.uuid4().hex
    job_dir = _JOBS_ROOT / job_id
    input_dir = job_dir / "input"
    ensure_dir(input_dir)

    image_suffix = Path(image.filename or "image.png").suffix or ".png"
    image_path = input_dir / f"image{image_suffix}"
    image_path.write_bytes(await image.read())

    volume_path: Path | None = None
    if volume and volume.filename:
        volume_suffix = Path(volume.filename).suffix or ".nii.gz"
        if volume_suffix == ".gz" and not str(volume.filename).endswith(".nii.gz"):
            volume_suffix = ".nii.gz"
        volume_path = input_dir / f"volume{volume_suffix}"
        volume_path.write_bytes(await volume.read())

    kwargs: dict[str, Any] = {"organ": meta.get("organ", "brain")}
    if volume_path is not None:
        kwargs["volume_path"] = str(volume_path)
    if meta.get("slice_axis"):
        kwargs["slice_axis"] = meta["slice_axis"]
    if meta.get("slice_index") is not None:
        kwargs["slice_index"] = int(meta["slice_index"])
    point = meta.get("point")
    if point and len(point) >= 2:
        kwargs["point"] = (int(point[0]), int(point[1]))
    bbox = meta.get("bbox")
    if bbox and len(bbox) >= 4:
        kwargs["bbox"] = tuple(int(v) for v in bbox[:4])

    peak_before = rss_mb()
    logger.info("remote_segment_start", extra={"job_id": job_id, "models": model_ids})
    try:
        results = _SEGMENT_SERVICE.segment_serial(str(image_path), model_ids, **kwargs)
    except Exception as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        logger.error("remote_segment_failed", extra={"job_id": job_id, "error": str(exc)})
        raise HTTPException(status_code=500, detail=f"Segmentation failed: {exc}") from exc
    peak_after = rss_mb()

    payload = _result_payload(results)
    payload, artifacts = _stage_artifacts(payload, job_dir)
    return {
        "job_id": job_id,
        "results": payload,
        "artifact_paths": artifacts,
        "memory_peak_mb": max(peak_before, peak_after),
    }


@app.get("/internal/jobs/{job_id}/artifact")
def download_artifact(job_id: str, path: str, _: AuthDep) -> FileResponse:
    if ".." in path or path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid artifact path")
    job_dir = (_JOBS_ROOT / job_id).resolve()
    target = (job_dir / path).resolve()
    if not str(target).startswith(str(job_dir)):
        raise HTTPException(status_code=400, detail="Invalid artifact path")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(target)


@app.delete("/internal/jobs/{job_id}")
def delete_job(job_id: str, _: AuthDep) -> dict[str, str]:
    job_dir = _JOBS_ROOT / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir, ignore_errors=True)
    return {"status": "deleted", "job_id": job_id}
