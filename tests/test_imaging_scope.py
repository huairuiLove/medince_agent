"""Unit tests for department-scoped imaging access."""
from __future__ import annotations

from src.auth.imaging_scope import (
    filter_models,
    filter_studies,
    path_allowed_for_sources,
    study_allowed_for_sources,
)
from src.schemas import ImagingStudyItem


def _study(source: str, study_id: str = "s1") -> ImagingStudyItem:
    return ImagingStudyItem(
        study_id=study_id,
        patient_id="p1",
        modality="XR",
        source=source,
        title="test",
        image_paths=[],
        slice_count=0,
    )


def test_filter_studies_respiratory_only_cxr():
    studies = [
        _study("mimic_cxr", "cxr1"),
        _study("brats2024", "mri1"),
        _study("chest_ct", "ct1"),
    ]
    out = filter_studies(studies, ["mimic_cxr"])
    assert len(out) == 1
    assert out[0].source == "mimic_cxr"


def test_filter_studies_empty_when_no_sources():
    assert filter_studies([_study("mimic_cxr")], []) == []


def test_filter_models_uses_dept_defaults():
    models = [
        {"model_id": "cxr_lesion", "datasets": ["mimic_cxr"]},
        {"model_id": "brats_tumor", "datasets": ["brats2024"]},
    ]
    out = filter_models(models, ["cxr_lesion", "sam2d"], ["mimic_cxr"])
    assert {m["model_id"] for m in out} == {"cxr_lesion"}


def test_path_allowed_for_sources():
    assert path_allowed_for_sources("datasets/mimic_cxr/foo.jpg", ["mimic_cxr"])
    assert not path_allowed_for_sources("datasets/brats2024/foo.nii.gz", ["mimic_cxr"])
    cxr_jpg = (
        "datasets/mimic/p10000764/s57375967/"
        "096052b7-d256dc40-453a102b-fa7d01c6-1b22c6b4.jpg"
    )
    assert path_allowed_for_sources(cxr_jpg, ["mimic_cxr"])
    assert path_allowed_for_sources(cxr_jpg, ["mimic"])
    assert not path_allowed_for_sources("data/imaging_cache/catalog/x.png", ["mimic_cxr"])
    assert not path_allowed_for_sources("data/imaging_cache/overlays/foo_overlay.png", ["mimic_cxr"])


def test_cache_path_scoped_by_study():
    patient = "BraTS-GLI-02405-100"
    study = "brats_BraTS-GLI-02405-100"
    assert study_allowed_for_sources(patient, study, ["brats2024"])
    assert not study_allowed_for_sources(patient, study, ["mimic_cxr"])
    seg = f"data/imaging_cache/segments/{patient}/{study}/seg_abc/model_overlay.png"
    assert path_allowed_for_sources(seg, ["brats2024"])
    assert not path_allowed_for_sources(seg, ["mimic_cxr"])


def test_cache_overlay_scoped_by_source_stem():
    cxr_jpg = (
        "datasets/mimic/p10000764/s57375967/"
        "096052b7-d256dc40-453a102b-fa7d01c6-1b22c6b4.jpg"
    )
    stem = "096052b7-d256dc40-453a102b-fa7d01c6-1b22c6b4"
    overlay = f"data/imaging_cache/overlays/{stem}_overlay.png"
    assert path_allowed_for_sources(overlay, ["mimic_cxr"])
    assert not path_allowed_for_sources(overlay, ["brats2024"])
    assert path_allowed_for_sources(cxr_jpg, ["mimic_cxr"])
