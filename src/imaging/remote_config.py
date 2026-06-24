"""Configuration helpers for remote imaging segmentation."""
from __future__ import annotations

from typing import Any

from src.config import get_config


def get_imaging_config() -> dict[str, Any]:
    return dict(get_config().get("imaging", {}) or {})


def get_remote_segment_config() -> dict[str, Any]:
    imaging = get_imaging_config()
    remote = dict(imaging.get("remote", {}) or {})
    worker = dict(remote.get("worker", {}) or {})
    return {
        "enabled": bool(remote.get("enabled", False)),
        "base_url": str(remote.get("base_url", "") or "").strip().rstrip("/"),
        "api_token": str(remote.get("api_token", "") or "").strip(),
        "timeout_seconds": int(remote.get("timeout_seconds", 600)),
        "fallback_to_local": bool(remote.get("fallback_to_local", True)),
        "health_cache_seconds": int(remote.get("health_cache_seconds", 30)),
        "worker_host": str(worker.get("host", "127.0.0.1") or "127.0.0.1"),
        "worker_port": int(worker.get("port", 9000)),
    }


def remote_segment_configured() -> bool:
    cfg = get_remote_segment_config()
    return bool(cfg["enabled"] and cfg["base_url"])
