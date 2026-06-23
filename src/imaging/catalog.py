"""Catalog of visual imaging studies from mimic (CT), mimic_cxr (XR), and brats2024 (MRI)."""
from __future__ import annotations

from pathlib import Path

from src.config import project_root, resolve_path
from src.imaging.cxr_manifest import load_manifest, rel_project_path
from src.imaging.volume_io import export_slice_png, is_visual_image, list_volume_slices
from src.schemas import ImagingStudyItem
from src.utils import ensure_dir


class ImagingCatalog:
    def __init__(self) -> None:
        self.mimic_dir = resolve_path("data/mimic")
        self.mimic_cxr_dir = resolve_path("data/mimic_cxr")
        self.brats_dir = resolve_path("data/brats2024")
        self.kits19_dir = resolve_path("data/kits19")
        self.cache_dir = resolve_path("data/imaging_cache/catalog")
        self._cxr_manifest = load_manifest()
        ensure_dir(self.cache_dir)

    def refresh_cxr_manifest(self) -> None:
        self._cxr_manifest = load_manifest()

    def _rel(self, path: Path) -> str:
        return rel_project_path(path)

    def list_studies(self, *, source: str | None = None) -> list[ImagingStudyItem]:
        studies: list[ImagingStudyItem] = []
        if source in (None, "", "mimic"):
            studies.extend(self._scan_mimic())
        if source in (None, "", "mimic_cxr"):
            studies.extend(self._scan_mimic_cxr())
        if source in (None, "", "brats2024"):
            studies.extend(self._scan_brats())
        if source in (None, "", "kits19"):
            studies.extend(self._scan_kits19())
        return studies

    def _scan_mimic(self) -> list[ImagingStudyItem]:
        items: list[ImagingStudyItem] = []
        if not self.mimic_dir.exists():
            return items
        for patient_dir in sorted(self.mimic_dir.iterdir()):
            if not patient_dir.is_dir() or patient_dir.name.startswith("."):
                continue
            for study_dir in sorted(patient_dir.iterdir()):
                if not study_dir.is_dir():
                    continue
                images = sorted(str(self._rel(p)) for p in study_dir.glob("*.jpg"))
                if not images:
                    continue
                items.append(
                    ImagingStudyItem(
                        study_id=f"mimic_{patient_dir.name}_{study_dir.name}",
                        patient_id=patient_dir.name,
                        modality="CT",
                        source="mimic",
                        title=f"MIMIC CT {patient_dir.name}/{study_dir.name}",
                        image_paths=images,
                        slice_count=len(images),
                    )
                )
        return items

    def _scan_mimic_cxr(self) -> list[ImagingStudyItem]:
        items: list[ImagingStudyItem] = []
        if not self.mimic_cxr_dir.exists():
            return items
        manifest_studies = self._cxr_manifest.get("studies") if isinstance(self._cxr_manifest, dict) else {}
        for patient_dir in sorted(self.mimic_cxr_dir.iterdir()):
            if not patient_dir.is_dir() or patient_dir.name.startswith("."):
                continue
            for study_dir in sorted(patient_dir.iterdir()):
                if not study_dir.is_dir():
                    continue
                study_key = f"mimic_cxr_{patient_dir.name}_{study_dir.name}"
                meta = manifest_studies.get(study_key) if isinstance(manifest_studies, dict) else None
                if isinstance(meta, dict) and meta.get("image_paths"):
                    images = [str(p) for p in meta["image_paths"]]
                else:
                    images = sorted(
                        self._rel(p) for p in study_dir.iterdir()
                        if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
                    )
                if not images:
                    continue
                collection = str(meta.get("collection", "") if meta else infer_collection_label(patient_dir.name))
                cxr_id = str(meta.get("cxr_id", "") if meta else "")
                report_text = str(meta.get("report_text", "") if meta else "")
                title_bits = [f"CXR {patient_dir.name}"]
                if collection:
                    title_bits.append(f"({collection})")
                if cxr_id:
                    title_bits.append(cxr_id)
                items.append(
                    ImagingStudyItem(
                        study_id=study_key,
                        patient_id=patient_dir.name,
                        modality="XR",
                        source="mimic_cxr",
                        title=" ".join(title_bits),
                        image_paths=images,
                        slice_count=len(images),
                        collection=collection,
                        report_text=report_text,
                        cxr_id=cxr_id,
                    )
                )
        return items

    def _scan_kits19(self) -> list[ImagingStudyItem]:
        items: list[ImagingStudyItem] = []
        if not self.kits19_dir.exists():
            return items
        for case_dir in sorted(self.kits19_dir.iterdir()):
            if not case_dir.is_dir() or case_dir.name.startswith("."):
                continue
            volume = case_dir / "imaging.nii.gz"
            if not volume.is_file():
                volume = next((p for p in case_dir.glob("*.nii.gz") if "seg" not in p.name.lower()), None)
            if volume is None:
                continue
            pngs: list[str] = []
            for idx in list_volume_slices(volume)[:8]:
                png = export_slice_png(volume, slice_index=idx, out_dir=self.cache_dir / case_dir.name)
                pngs.append(self._rel(png))
            items.append(
                ImagingStudyItem(
                    study_id=f"kits19_{case_dir.name}",
                    patient_id=case_dir.name,
                    modality="CT",
                    source="kits19",
                    title=f"KiTS19 Renal CT {case_dir.name}",
                    image_paths=pngs,
                    volume_path=self._rel(volume),
                    slice_count=len(pngs),
                    collection="KiTS19",
                )
            )
        return items

    def _scan_brats(self) -> list[ImagingStudyItem]:
        items: list[ImagingStudyItem] = []
        if not self.brats_dir.exists():
            return items
        for case_dir in sorted(self.brats_dir.iterdir()):
            if not case_dir.is_dir() or case_dir.name.startswith("."):
                continue
            volumes = [p for p in case_dir.glob("*.nii.gz") if "seg" not in p.name.lower()]
            if not volumes:
                continue
            primary = next((p for p in volumes if "t1c" in p.name.lower()), volumes[0])
            pngs: list[str] = []
            for idx in list_volume_slices(primary)[:8]:
                png = export_slice_png(primary, slice_index=idx, out_dir=self.cache_dir / case_dir.name)
                pngs.append(self._rel(png))
            items.append(
                ImagingStudyItem(
                    study_id=f"brats_{case_dir.name}",
                    patient_id=case_dir.name,
                    modality="MRI",
                    source="brats2024",
                    title=f"BraTS MRI {case_dir.name}",
                    image_paths=pngs,
                    volume_path=self._rel(primary),
                    slice_count=len(pngs),
                )
            )
        return items

    def get_study(self, study_id: str) -> ImagingStudyItem | None:
        for s in self.list_studies():
            if s.study_id == study_id:
                return s
        return None

    def resolve_visual_only(self, path: str) -> str:
        p = Path(path)
        if not p.is_absolute():
            p = project_root() / path
        if is_visual_image(p):
            return self._rel(p)
        if str(p).endswith(".nii.gz") or p.suffix == ".nii":
            return self._rel(export_slice_png(p))
        raise ValueError(f"Not a visual image path: {path}")


def infer_collection_label(patient_id: str) -> str:
    if patient_id.startswith("p_nlmcxr_"):
        return "NLMCXR"
    if patient_id.startswith("p") and patient_id[1:].isdigit():
        return "MIMIC-CXR"
    return "local"
