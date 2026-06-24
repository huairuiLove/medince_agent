"""HTTP client for remote segment worker."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from src.config import resolve_path
from src.imaging.backends.base import SegmentResult
from src.imaging.remote_config import get_remote_segment_config, remote_segment_configured
from src.imaging.registry import ModelId
from src.logging_config import get_logger
from src.utils import ensure_dir

logger = get_logger("imaging.remote_client")

_HEALTH_CACHE: dict[str, Any] = {"checked_at": 0.0, "ok": False, "detail": ""}


@dataclass
class RemoteSegmentOutcome:
    ok: bool
    results: list[SegmentResult] | None = None
    memory_peak_mb: float = 0.0
    error: str = ""
    job_id: str = ""


def _auth_headers(cfg: dict[str, Any]) -> dict[str, str]:
    token = cfg.get("api_token") or ""
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def check_remote_health(*, force: bool = False) -> tuple[bool, str]:
    if not remote_segment_configured():
        return False, "remote segment not configured"

    cfg = get_remote_segment_config()
    cache_ttl = max(0, int(cfg["health_cache_seconds"]))
    now = time.time()
    if not force and cache_ttl and (now - float(_HEALTH_CACHE["checked_at"])) < cache_ttl:
        return bool(_HEALTH_CACHE["ok"]), str(_HEALTH_CACHE["detail"])

    detail = ""
    ok = False
    try:
        with httpx.Client(timeout=min(15, int(cfg["timeout_seconds"]))) as client:
            res = client.get(f"{cfg['base_url']}/health", headers=_auth_headers(cfg))
            res.raise_for_status()
            body = res.json()
            if str(body.get("status", "")).lower() != "ok":
                detail = f"worker status={body.get('status')}"
            else:
                ok = True
                detail = "reachable"
    except Exception as exc:
        detail = str(exc)

    _HEALTH_CACHE["checked_at"] = now
    _HEALTH_CACHE["ok"] = ok
    _HEALTH_CACHE["detail"] = detail
    return ok, detail


def remote_segment_status() -> dict[str, Any]:
    cfg = get_remote_segment_config()
    configured = remote_segment_configured()
    reachable, detail = check_remote_health() if configured else (False, "disabled")
    return {
        "enabled": cfg["enabled"],
        "configured": configured,
        "reachable": reachable,
        "base_url": cfg["base_url"],
        "fallback_to_local": cfg["fallback_to_local"],
        "detail": detail,
    }


def _rewrite_paths(value: Any, path_map: dict[str, str]) -> Any:
    if isinstance(value, str) and value in path_map:
        return path_map[value]
    if isinstance(value, dict):
        return {k: _rewrite_paths(v, path_map) for k, v in value.items()}
    if isinstance(value, list):
        return [_rewrite_paths(v, path_map) for v in value]
    return value


def _download_artifacts(
    cfg: dict[str, Any],
    job_id: str,
    artifact_paths: list[str],
) -> dict[str, str]:
    pull_root = resolve_path(f"data/imaging_cache/remote_pull/{job_id}")
    ensure_dir(pull_root)
    path_map: dict[str, str] = {}
    project_root = resolve_path(".")

    with httpx.Client(timeout=int(cfg["timeout_seconds"])) as client:
        for rel in artifact_paths:
            url = f"{cfg['base_url']}/internal/jobs/{job_id}/artifact"
            res = client.get(url, params={"path": rel}, headers=_auth_headers(cfg))
            res.raise_for_status()
            local_path = pull_root / rel
            ensure_dir(local_path.parent)
            local_path.write_bytes(res.content)
            path_map[rel] = local_path.resolve().relative_to(project_root.resolve()).as_posix()

        try:
            client.delete(
                f"{cfg['base_url']}/internal/jobs/{job_id}",
                headers=_auth_headers(cfg),
            )
        except Exception as exc:
            logger.warning("remote_job_cleanup_failed", extra={"job_id": job_id, "error": str(exc)})

    return path_map


def _payload_to_results(payload: list[dict[str, Any]], path_map: dict[str, str]) -> list[SegmentResult]:
    results: list[SegmentResult] = []
    for item in payload:
        rewritten = _rewrite_paths(item, path_map)
        stats = rewritten.get("stats") or {}
        results.append(
            SegmentResult(
                model_id=str(rewritten["model_id"]),
                source_image=str(rewritten.get("source_image", "")),
                overlay_path=str(rewritten.get("overlay_path", "")),
                mask_path=rewritten.get("mask_path"),
                labels=list(rewritten.get("labels") or []),
                stats=dict(stats) if isinstance(stats, dict) else {},
                memory_mb=float(rewritten.get("memory_mb") or 0),
                duration_ms=float(rewritten.get("duration_ms") or 0),
                notes=str(rewritten.get("notes") or ""),
            )
        )
    return results


def run_remote_segment(
    *,
    model_ids: list[ModelId],
    image_path: Path,
    volume_path: Path | None,
    organ: str,
    slice_axis: str,
    slice_index: int | None,
    point: list[int] | None = None,
    bbox: list[int] | None = None,
) -> RemoteSegmentOutcome:
    cfg = get_remote_segment_config()
    if not remote_segment_configured():
        return RemoteSegmentOutcome(ok=False, error="remote segment not configured")

    if not image_path.is_file():
        return RemoteSegmentOutcome(ok=False, error=f"image not found: {image_path}")

    metadata = {
        "model_ids": model_ids,
        "organ": organ,
        "slice_axis": slice_axis,
        "slice_index": slice_index,
        "point": point,
        "bbox": bbox,
    }

    files: list[tuple[str, tuple[str, bytes, str]]] = []
    image_bytes = image_path.read_bytes()
    image_mime = "application/gzip" if image_path.suffix == ".gz" else "image/png"
    if image_path.suffix.lower() in {".jpg", ".jpeg"}:
        image_mime = "image/jpeg"
    files.append(("image", (image_path.name, image_bytes, image_mime)))

    if volume_path is not None:
        if not volume_path.is_file():
            return RemoteSegmentOutcome(ok=False, error=f"volume not found: {volume_path}")
        files.append(("volume", (volume_path.name, volume_path.read_bytes(), "application/gzip")))

    data = {"metadata": json.dumps(metadata, ensure_ascii=False)}

    try:
        with httpx.Client(timeout=int(cfg["timeout_seconds"])) as client:
            res = client.post(
                f"{cfg['base_url']}/internal/segment",
                data=data,
                files=files,
                headers=_auth_headers(cfg),
            )
            res.raise_for_status()
            body = res.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        try:
            detail = exc.response.json().get("detail", detail)
        except Exception:
            pass
        return RemoteSegmentOutcome(ok=False, error=f"remote HTTP {exc.response.status_code}: {detail}")
    except Exception as exc:
        return RemoteSegmentOutcome(ok=False, error=str(exc))

    job_id = str(body.get("job_id") or "")
    artifact_paths = list(body.get("artifact_paths") or [])
    try:
        path_map = _download_artifacts(cfg, job_id, artifact_paths)
    except Exception as exc:
        return RemoteSegmentOutcome(ok=False, error=f"artifact download failed: {exc}", job_id=job_id)

    payload = list(body.get("results") or [])
    results = _payload_to_results(payload, path_map)
    return RemoteSegmentOutcome(
        ok=True,
        results=results,
        memory_peak_mb=float(body.get("memory_peak_mb") or 0),
        job_id=job_id,
    )
