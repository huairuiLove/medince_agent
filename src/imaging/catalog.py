"""Catalog of visual imaging studies from mimic (CT JPG) and brats2024 (MRI slices)."""
from __future__ import annotations

from pathlib import Path

from src.config import resolve_path
from src.imaging.volume_io import export_slice_png, guess_modality, is_visual_image, list_volume_slices
from src.schemas import ImagingStudyItem
from src.utils import ensure_dir


class ImagingCatalog:
    def __init__(self) -> None:
        self.mimic_dir = resolve_path("data/mimic")
        self.brats_dir = resolve_path("data/brats2024")
        self.cache_dir = resolve_path("data/imaging_cache/catalog")
        ensure_dir(self.cache_dir)

    def list_studies(self) -> list[ImagingStudyItem]:
        studies: list[ImagingStudyItem] = []
        studies.extend(self._scan_mimic())
        studies.extend(self._scan_brats())
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
                images = sorted(str(p) for p in study_dir.glob("*.jpg"))
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
                pngs.append(str(png))
            items.append(
                ImagingStudyItem(
                    study_id=f"brats_{case_dir.name}",
                    patient_id=case_dir.name,
                    modality="MRI",
                    source="brats2024",
                    title=f"BraTS MRI {case_dir.name}",
                    image_paths=pngs,
                    volume_path=str(primary),
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
        if is_visual_image(p):
            return str(p)
        if str(p).endswith(".nii.gz") or p.suffix == ".nii":
            return str(export_slice_png(p))
        raise ValueError(f"Not a visual image path: {path}")
