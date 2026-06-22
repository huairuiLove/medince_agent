"""Department-scoped imaging access."""
from __future__ import annotations

from src.imaging.registry import MODEL_REGISTRY, ModelId
from src.schemas import ImagingStudyItem


def filter_studies(studies: list[ImagingStudyItem], imaging_sources: list[str]) -> list[ImagingStudyItem]:
    if not imaging_sources:
        return []
    allowed = set(imaging_sources)
    return [s for s in studies if s.source in allowed]


def filter_models(models: list[dict], dept_default_models: list[str], imaging_sources: list[str]) -> list[dict]:
    if not imaging_sources:
        return []
    allowed_sources = set(imaging_sources)
    if dept_default_models:
        allowed_ids = set(dept_default_models)
        return [m for m in models if m.get("model_id") in allowed_ids]
    return [
        m
        for m in models
        if any(ds in allowed_sources for ds in m.get("datasets", []))
    ]


def default_models_for_sources(imaging_sources: list[str]) -> list[str]:
    if not imaging_sources:
        return []
    ids: list[str] = []
    for model_id, spec in MODEL_REGISTRY.items():
        if any(ds in imaging_sources for ds in spec.datasets):
            ids.append(model_id)
    return ids
