"""Imaging analysis cache store tests."""

from __future__ import annotations

from pathlib import Path

from src.imaging.analysis_cache import ImagingAnalysisCacheStore
from src.schemas import ImagingAnalysisCacheEntry


def test_analysis_cache_roundtrip(tmp_path: Path) -> None:
    store = ImagingAnalysisCacheStore(base_dir=tmp_path)
    entry = ImagingAnalysisCacheEntry(
        patient_id="p1",
        study_id="s1",
        source="mimic_cxr",
        modality="XR",
        image_paths=["datasets/mimic/x.png"],
        vlm_analysis={"clinical_analysis": "ok"},
        vlm_model="qwen-test",
        deepseek_synthesis={"risk_summary": "low"},
        deepseek_model="deepseek-test",
    )
    saved = store.save(entry)
    assert saved.created_at
    loaded = store.get("mimic_cxr", "p1", "s1")
    assert loaded is not None
    assert loaded.vlm_analysis["clinical_analysis"] == "ok"
    assert loaded.deepseek_synthesis["risk_summary"] == "low"
