"""Department-scoped imaging access."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from src.auth.models import UserProfile
from src.config import resolve_path
from src.imaging.cxr_manifest import is_mimic_cxr_jpg_patient, is_mimic_cxr_jpg_study
from src.imaging.registry import MODEL_REGISTRY
from src.schemas import ImagingStudyItem

# Catalog source id → on-disk dataset roots (relative to project root)
SOURCE_DATASET_DIRS: dict[str, tuple[str, ...]] = {
    "mimic_cxr": ("datasets/mimic_cxr",),
    "mimic": ("datasets/mimic",),
    "brats2024": ("datasets/brats2024",),
    "kits19": ("datasets/kits19",),
    "chest_ct": ("datasets/chest_ct",),
}

IMAGING_CACHE_PREFIX = "data/imaging_cache/"
_MPR_AXES = ("axial", "coronal", "sagittal")


def _rel_imaging_path(path: str) -> str | None:
    root = resolve_path(".")
    target = Path(path)
    if not target.is_absolute():
        target = (root / path).resolve()
    else:
        target = target.resolve()
    root_resolved = root.resolve()
    if not str(target).startswith(str(root_resolved)):
        return None
    return target.relative_to(root_resolved).as_posix()


def _mimic_cxr_jpg_under_mimic(rel: str) -> bool:
    """Official MIMIC-CXR-JPG is indexed as source=mimic_cxr but stored under datasets/mimic/."""
    parts = rel.split("/")
    if len(parts) < 5 or parts[0] != "datasets" or parts[1] != "mimic":
        return False
    patient_id, study_id = parts[2], parts[3]
    if not is_mimic_cxr_jpg_patient(patient_id):
        return False
    return is_mimic_cxr_jpg_study(study_id)


@lru_cache(maxsize=1)
def _catalog_studies() -> tuple[ImagingStudyItem, ...]:
    from src.imaging.catalog import ImagingCatalog

    return tuple(ImagingCatalog().list_studies())


def _filtered_studies(imaging_sources: list[str]) -> list[ImagingStudyItem]:
    return filter_studies(list(_catalog_studies()), imaging_sources)


def study_allowed_for_sources(patient_id: str, study_id: str, imaging_sources: list[str]) -> bool:
    if not imaging_sources:
        return False
    allowed = set(imaging_sources)
    for s in _catalog_studies():
        if s.patient_id != patient_id or s.study_id != study_id:
            continue
        if s.source in allowed:
            return True
    return False


def _catalog_case_allowed(case_dir: str, imaging_sources: list[str]) -> bool:
    for s in _filtered_studies(imaging_sources):
        if s.patient_id == case_dir or case_dir in s.study_id:
            return True
    return False


def _file_stem_allowed(stem: str, imaging_sources: list[str]) -> bool:
    if not stem:
        return False
    for s in _filtered_studies(imaging_sources):
        if s.volume_path:
            vp = Path(s.volume_path)
            if vp.stem == stem or stem in s.volume_path or vp.parent.name == stem:
                return True
        for img in s.image_paths:
            ip = Path(img)
            if ip.stem == stem or stem in img:
                return True
    return False


def _overlay_stem(filename: str) -> str:
    for suffix in ("_overlay.png", "_overlay.PNG"):
        if filename.endswith(suffix):
            return filename[: -len(suffix)]
    return Path(filename).stem


def _mpr_stem(filename: str) -> str:
    for axis in _MPR_AXES:
        marker = f"_{axis}_"
        if marker in filename:
            return filename.split(marker, 1)[0]
    return Path(filename).stem


def _pseudo_vol_stem(filename: str) -> str:
    if "_pseudo_d" in filename:
        return filename.split("_pseudo_d", 1)[0]
    name = filename
    if name.endswith(".nii.gz"):
        name = name[: -len(".nii.gz")]
    return Path(name).stem


def _cache_path_allowed(rel: str, imaging_sources: list[str]) -> bool:
    if not imaging_sources or not rel.startswith(IMAGING_CACHE_PREFIX):
        return False

    parts = rel.split("/")
    if len(parts) < 4:
        return False

    sub = parts[2]

    if sub in {"segments", "screenshots"} and len(parts) >= 5:
        return study_allowed_for_sources(parts[3], parts[4], imaging_sources)

    if sub == "catalog" and len(parts) >= 4:
        return _catalog_case_allowed(parts[3], imaging_sources)

    if sub == "overlays" and len(parts) >= 4:
        return _file_stem_allowed(_overlay_stem(parts[3]), imaging_sources)

    if sub == "slices" and len(parts) >= 4:
        case_dir = parts[3]
        if _catalog_case_allowed(case_dir, imaging_sources):
            return True
        fn = parts[4] if len(parts) >= 5 else ""
        if fn.startswith(f"{case_dir}_"):
            return True
        stem = fn.split("_z", 1)[0] if "_z" in fn else Path(fn).stem
        return _file_stem_allowed(stem, imaging_sources) or _file_stem_allowed(case_dir, imaging_sources)

    if sub == "mpr" and len(parts) >= 4:
        return _file_stem_allowed(_mpr_stem(parts[3]), imaging_sources)

    if sub in {"vista3d", "totalseg", "brats_tumor"} and len(parts) >= 4:
        return _file_stem_allowed(parts[3], imaging_sources)

    if sub == "brats_input" and len(parts) >= 4:
        return _file_stem_allowed(Path(parts[3]).stem, imaging_sources)

    if sub == "pseudo_vol" and len(parts) >= 4:
        return _file_stem_allowed(_pseudo_vol_stem(parts[3]), imaging_sources)

    return False


def imaging_sources_for_user(user: UserProfile) -> list[str]:
    dept = user.department
    if dept and dept.imaging_sources:
        return list(dept.imaging_sources)
    return []


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


def allowed_model_ids(models: list[dict], dept_default_models: list[str], imaging_sources: list[str]) -> set[str]:
    return {str(m.get("model_id")) for m in filter_models(models, dept_default_models, imaging_sources)}


def default_models_for_sources(imaging_sources: list[str]) -> list[str]:
    if not imaging_sources:
        return []
    ids: list[str] = []
    for model_id, spec in MODEL_REGISTRY.items():
        if any(ds in imaging_sources for ds in spec.datasets):
            ids.append(model_id)
    return ids


def path_allowed_for_sources(path: str, imaging_sources: list[str]) -> bool:
    if not imaging_sources:
        return False
    rel = _rel_imaging_path(path)
    if rel is None:
        return False

    if rel.startswith(IMAGING_CACHE_PREFIX):
        return _cache_path_allowed(rel, imaging_sources)

    allowed_prefixes: list[str] = []
    for src in imaging_sources:
        for dataset_dir in SOURCE_DATASET_DIRS.get(src, ()):
            allowed_prefixes.append(f"{dataset_dir}/")

    if any(rel.startswith(prefix) for prefix in allowed_prefixes):
        return True

    if "mimic_cxr" in imaging_sources and _mimic_cxr_jpg_under_mimic(rel):
        return True

    return False
