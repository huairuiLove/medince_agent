"""Build and load metadata for chest X-rays under datasets/mimic_cxr/ and official MIMIC-CXR-JPG in datasets/mimic/."""
from __future__ import annotations

import json
import re
import tarfile
import xml.etree.ElementTree as ET
from pathlib import Path

from src.config import datasets_path, project_root, resolve_path
from src.utils import ensure_dir, save_json

_MANIFEST_NAME = "studies_manifest.json"
_CXR_ID_RE = re.compile(r"^(CXR\d+)", re.I)
_NLMCXR_INDEX_RE = re.compile(r"^p_nlmcxr_(\d+)$", re.I)
_MIMIC_CXR_PATIENT_RE = re.compile(r"^p\d{8}$", re.I)
_MIMIC_CXR_STUDY_RE = re.compile(r"^s\d+$", re.I)
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def manifest_path() -> Path:
    return datasets_path("mimic_cxr") / _MANIFEST_NAME


def nlmcxr_png_root() -> Path:
    return datasets_path("external/nlmcxr/NLMCXR_png")


def nlmcxr_reports_dir() -> Path:
    return datasets_path("external/nlmcxr/ecgen-radiology")


def nlmcxr_reports_archive() -> Path:
    return datasets_path("external/nlmcxr/NLMCXR_reports.tgz")


def rel_project_path(path: Path) -> str:
    root = project_root().resolve()
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(root))
    except ValueError:
        return str(resolved)


def cxr_id_from_filename(name: str) -> str | None:
    match = _CXR_ID_RE.match(Path(name).stem)
    return match.group(1).upper() if match else None


def pmc_id_from_cxr_id(cxr_id: str) -> str | None:
    if cxr_id.upper().startswith("CXR"):
        digits = cxr_id[3:]
        return digits if digits.isdigit() else None
    return None


def ensure_reports_extracted(*, force: bool = False) -> Path:
    dest = nlmcxr_reports_dir()
    archive = nlmcxr_reports_archive()
    if not archive.is_file():
        return dest
    xml_count = len(list(dest.glob("*.xml"))) if dest.is_dir() else 0
    if force or xml_count < 100:
        ensure_dir(dest.parent)
        with tarfile.open(archive, "r:gz") as tar:
            try:
                tar.extractall(path=dest.parent, filter="data")
            except TypeError:
                tar.extractall(path=dest.parent)
    return dest


def parse_report_xml(path: Path) -> tuple[str, str]:
    """Return (cxr_uid, plain-text report)."""
    root = ET.parse(path).getroot()
    uid = ""
    uid_el = root.find("uId")
    if uid_el is not None and uid_el.get("id"):
        uid = uid_el.get("id", "")
    parts: list[str] = []
    for abstract in root.iter("AbstractText"):
        label = abstract.get("Label", "").strip()
        text = (abstract.text or "").strip()
        if not text:
            continue
        if label:
            parts.append(f"{label}: {text}")
        else:
            parts.append(text)
    return uid, "\n".join(parts)


def load_report_text(cxr_id: str) -> str:
    pmc = pmc_id_from_cxr_id(cxr_id)
    if not pmc:
        return ""
    reports_dir = ensure_reports_extracted()
    report_path = reports_dir / f"{pmc}.xml"
    if not report_path.is_file():
        return ""
    _, text = parse_report_xml(report_path)
    return text


def resolve_nlmcxr_source_file(patient_id: str) -> str | None:
    match = _NLMCXR_INDEX_RE.match(patient_id)
    if not match:
        return None
    index = int(match.group(1))
    png_root = nlmcxr_png_root()
    if not png_root.is_dir():
        return None
    png_files = sorted(png_root.rglob("*.png"))
    if index < 1 or index > len(png_files):
        return None
    return png_files[index - 1].name


def infer_collection(patient_id: str) -> str:
    if _NLMCXR_INDEX_RE.match(patient_id):
        return "NLMCXR"
    if is_mimic_cxr_jpg_patient(patient_id):
        return "MIMIC-CXR-JPG"
    return "local"


def is_mimic_cxr_jpg_patient(patient_id: str) -> bool:
    return bool(_MIMIC_CXR_PATIENT_RE.match(patient_id))


def is_mimic_cxr_jpg_study(study_id: str) -> bool:
    return bool(_MIMIC_CXR_STUDY_RE.match(study_id))


def iter_study_images(study_dir: Path) -> list[Path]:
    return sorted(
        p for p in study_dir.iterdir()
        if p.is_file() and p.suffix.lower() in _IMAGE_SUFFIXES
    )


def load_mimic_cxr_jpg_report(patient_dir: Path, study_id: str) -> str:
    report_path = patient_dir / f"{study_id}.txt"
    if not report_path.is_file():
        return ""
    return report_path.read_text(encoding="utf-8", errors="replace").strip()


def study_key(patient_id: str, study_folder: str) -> str:
    return f"mimic_cxr_{patient_id}_{study_folder}"


def register_study(
    studies: dict[str, dict],
    *,
    patient_id: str,
    study_folder: str,
    images: list[Path],
    collection: str,
    report_text: str = "",
    source_file: str = "",
    cxr_id: str = "",
) -> None:
    if not images:
        return
    key = study_key(patient_id, study_folder)
    studies[key] = {
        "study_id": key,
        "patient_id": patient_id,
        "study_folder": study_folder,
        "collection": collection,
        "source_file": source_file or images[0].name,
        "cxr_id": cxr_id,
        "image_count": len(images),
        "primary_image": rel_project_path(images[0]),
        "image_paths": [rel_project_path(p) for p in images],
        "report_text": report_text,
    }


def scan_mimic_cxr_jpg_root(root: Path, studies: dict[str, dict]) -> set[str]:
    """Index official PhysioNet MIMIC-CXR-JPG layout under datasets/mimic/."""
    indexed: set[str] = set()
    if not root.is_dir():
        return indexed
    for patient_dir in sorted(root.iterdir()):
        if not patient_dir.is_dir() or patient_dir.name.startswith("."):
            continue
        if not is_mimic_cxr_jpg_patient(patient_dir.name):
            continue
        for study_dir in sorted(patient_dir.iterdir()):
            if not study_dir.is_dir() or not is_mimic_cxr_jpg_study(study_dir.name):
                continue
            images = iter_study_images(study_dir)
            if not images:
                continue
            report_text = load_mimic_cxr_jpg_report(patient_dir, study_dir.name)
            register_study(
                studies,
                patient_id=patient_dir.name,
                study_folder=study_dir.name,
                images=images,
                collection="MIMIC-CXR-JPG",
                report_text=report_text,
            )
            indexed.add(patient_dir.name)
    return indexed


def scan_cxr_drop_root(
    root: Path,
    studies: dict[str, dict],
    *,
    skip_patients: set[str] | None = None,
) -> None:
    """Index NLMCXR / supplemental PNGs under datasets/mimic_cxr/."""
    if not root.is_dir():
        return
    skip = skip_patients or set()
    for patient_dir in sorted(root.iterdir()):
        if not patient_dir.is_dir() or patient_dir.name.startswith("."):
            continue
        if patient_dir.name in skip and is_mimic_cxr_jpg_patient(patient_dir.name):
            continue
        for study_dir in sorted(patient_dir.iterdir()):
            if not study_dir.is_dir():
                continue
            images = iter_study_images(study_dir)
            if not images:
                continue
            key = study_key(patient_dir.name, study_dir.name)
            if key in studies:
                continue
            source_file = resolve_nlmcxr_source_file(patient_dir.name) or images[0].name
            cxr_id = cxr_id_from_filename(source_file) or ""
            report_text = load_report_text(cxr_id) if cxr_id else ""
            register_study(
                studies,
                patient_id=patient_dir.name,
                study_folder=study_dir.name,
                images=images,
                collection=infer_collection(patient_dir.name),
                report_text=report_text,
                source_file=source_file,
                cxr_id=cxr_id,
            )


def build_manifest(*, force_reports: bool = False) -> dict:
    """Scan official MIMIC-CXR-JPG (datasets/mimic/) and supplemental CXR (datasets/mimic_cxr/)."""
    ensure_reports_extracted(force=force_reports)
    studies: dict[str, dict] = {}
    mimic_jpg_root = datasets_path("mimic")
    cxr_root = datasets_path("mimic_cxr")
    official_patients = scan_mimic_cxr_jpg_root(mimic_jpg_root, studies)
    scan_cxr_drop_root(cxr_root, studies, skip_patients=official_patients)
    return {"version": 1, "study_count": len(studies), "studies": studies}


def save_manifest(data: dict | None = None) -> Path:
    payload = data if data is not None else build_manifest()
    out = manifest_path()
    ensure_dir(out.parent)
    save_json(payload, out)
    return out


def load_manifest() -> dict:
    path = manifest_path()
    if not path.is_file():
        return {"version": 1, "study_count": 0, "studies": {}}
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def get_study_meta(study_id: str) -> dict | None:
    studies = load_manifest().get("studies") or {}
    if isinstance(studies, dict):
        item = studies.get(study_id)
        return item if isinstance(item, dict) else None
    return None
