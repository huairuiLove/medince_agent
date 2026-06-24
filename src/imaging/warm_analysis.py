"""Build or load per-study imaging analysis cache using source images only."""
from __future__ import annotations

import time
from pathlib import Path

from src.config import project_root, resolve_path
from src.imaging.analysis_cache import ImagingAnalysisCacheStore
from src.imaging.catalog import ImagingCatalog
from src.imaging.volume_io import export_slice_png, is_nifti, resolve_vlm_image_paths
from src.llm.errors import LLMNotConfiguredError
from src.llm.vision_client import get_deepseek_client, get_qwen_vlm_client
from src.schemas import ImagingAnalysisCacheEntry, ImagingStudyItem


def find_study(patient_id: str, study_id: str, source: str = "") -> ImagingStudyItem | None:
    catalog = ImagingCatalog()
    for study in catalog.list_studies(source=source or None):
        if study.patient_id == patient_id and study.study_id == study_id:
            return study
    return None


def resolve_study_source_images(study: ImagingStudyItem, *, max_images: int = 4) -> list[str]:
    """Raster paths for VLM — catalog previews or a single volume slice, never overlays."""
    rel_paths = [p for p in (study.image_paths or []) if p]
    if not rel_paths and study.volume_path:
        vol = (project_root() / study.volume_path).resolve()
        if vol.exists() and is_nifti(vol):
            png = export_slice_png(vol)
            rel_paths = [str(png.relative_to(project_root()))]
    abs_paths: list[str] = []
    for rel in rel_paths:
        target = (project_root() / rel).resolve()
        if target.exists():
            abs_paths.append(str(target))
    resolved = resolve_vlm_image_paths(abs_paths)
    return resolved[:max_images]


def _rel_paths(abs_paths: list[str]) -> list[str]:
    root = project_root().resolve()
    out: list[str] = []
    for p in abs_paths:
        try:
            out.append(str(Path(p).resolve().relative_to(root)))
        except ValueError:
            out.append(p)
    return out


def warm_study_analysis(
    study: ImagingStudyItem,
    *,
    clinical_text: str = "",
    force: bool = False,
    include_deepseek: bool = True,
) -> ImagingAnalysisCacheEntry:
    store = ImagingAnalysisCacheStore()
    if not force:
        existing = store.get(study.source, study.patient_id, study.study_id)
        if existing:
            return existing

    images_abs = resolve_study_source_images(study)
    if not images_abs:
        raise ValueError(f"No source images for study {study.patient_id}/{study.study_id}")

    summary = (clinical_text or study.report_text or f"{study.title} — {study.modality}").strip()
    qwen = get_qwen_vlm_client()
    t0 = time.perf_counter()
    vlm_analysis = qwen.analyze_images(
        images=images_abs,
        patient_summary=summary,
        modality=study.modality,
        task="clinical_and_medication",
    )
    vlm_ms = round((time.perf_counter() - t0) * 1000, 1)

    deepseek_synthesis: dict = {}
    ds_model = ""
    if include_deepseek:
        try:
            deepseek = get_deepseek_client()
            deepseek_synthesis = deepseek.synthesize_report(
                clinical_text=summary,
                vlm_analysis=vlm_analysis,
                agent_opinions=[],
                arbitration={},
                rule_output={},
                chain_hint=str(vlm_analysis.get("reasoning", "")),
            )
            ds_model = deepseek.model_name
        except LLMNotConfiguredError:
            deepseek_synthesis = {}

    rel_images = _rel_paths(images_abs)
    entry = ImagingAnalysisCacheEntry(
        patient_id=study.patient_id,
        study_id=study.study_id,
        source=study.source,
        modality=study.modality,
        title=study.title,
        image_paths=rel_images,
        clinical_text=summary,
        vlm_analysis=vlm_analysis,
        vlm_model=qwen.model_name,
        vlm_duration_ms=vlm_ms,
        deepseek_synthesis=deepseek_synthesis,
        deepseek_model=ds_model,
        created_at="",
        updated_at="",
    )
    return store.save(entry)


def get_or_run_study_analysis(
    study: ImagingStudyItem,
    *,
    clinical_text: str = "",
    use_cache: bool = True,
    force_refresh: bool = False,
    include_deepseek: bool = True,
) -> tuple[ImagingAnalysisCacheEntry, bool]:
    """Return (entry, from_cache)."""
    store = ImagingAnalysisCacheStore()
    if use_cache and not force_refresh:
        cached = store.get(study.source, study.patient_id, study.study_id)
        if cached:
            return cached, True
    entry = warm_study_analysis(
        study,
        clinical_text=clinical_text,
        force=True,
        include_deepseek=include_deepseek,
    )
    return entry, False
