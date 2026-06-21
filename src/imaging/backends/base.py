"""Base class for serial 2D segmentation backends."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SegmentResult:
    model_id: str
    source_image: str
    overlay_path: str
    mask_path: str | None = None
    labels: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    memory_mb: float = 0.0
    duration_ms: float = 0.0
    notes: str = ""


class BaseSegmentBackend(ABC):
    model_id: str

    @abstractmethod
    def segment(self, image_path: str | Path, **kwargs: Any) -> SegmentResult:
        raise NotImplementedError

    @abstractmethod
    def unload(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError
