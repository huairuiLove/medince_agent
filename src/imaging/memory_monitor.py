"""Process memory monitoring for serial model inference on 16GB devices."""
from __future__ import annotations

import gc
import resource
import sys
from dataclasses import dataclass, field
from typing import Any

from src.logging_config import get_logger

logger = get_logger("imaging.memory")


@dataclass
class MemorySnapshot:
    rss_mb: float
    label: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def rss_mb() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return usage / (1024 * 1024)
    return usage / 1024


def snapshot(label: str = "", **extra: Any) -> MemorySnapshot:
    snap = MemorySnapshot(rss_mb=rss_mb(), label=label, extra=extra)
    logger.info("memory_snapshot", extra={"label": label, "rss_mb": round(snap.rss_mb, 1), **extra})
    return snap


def release_torch() -> None:
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        if hasattr(torch, "mps") and torch.backends.mps.is_available():
            torch.mps.empty_cache()
    except ImportError:
        pass
    gc.collect()


def memory_delta(before: MemorySnapshot, after: MemorySnapshot) -> float:
    return after.rss_mb - before.rss_mb
