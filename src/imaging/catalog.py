"""Catalog of visual imaging studies: mimic_cxr (XR), chest_ct / kits19 (CT), brats2024 (MRI)."""
from __future__ import annotations

from pathlib import Path

from src.config import datasets_path, project_root, resolve_path
from src.imaging.cxr_manifest import (
    is_mimic_cxr_jpg_patient,
    is_mimic_cxr_jpg_study,
    iter_study_images,
    load_manifest,
    load_mimic_cxr_jpg_report,
    rel_project_path,
    study_key,
)
from src.imaging.volume_io import export_slice_png, is_visual_image, list_volume_slices
from src.schemas import ImagingStudyItem
from src.utils import ensure_dir


class ImagingCatalog:
    def __init__(self) -> None:
        self.mimic_dir = datasets_path("mimic")
        self.mimic_cxr_dir = datasets_path("mimic_cxr")
        self.brats_dir = datasets_path("brats2024")
        self.kits19_dir = datasets_path("kits19")
        self.chest_ct_dir = datasets_path("chest_ct")
        self.cache_dir = resolve_path("data/imaging_cache/catalog")
        self._preview_slices = 4
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
        if source in (None, "", "chest_ct"):
            studies.extend(self._scan_chest_ct())
        return studies

    def _volume_previews(self, volume: Path, cache_subdir: str) -> list[str]:
        slices = list_volume_slices(volume)[: self._preview_slices]
        out_dir = self.cache_dir / cache_subdir
        cached: list[str] = []
        for idx in slices:
            out = out_dir / f"{volume.stem}_z{idx:04d}.png"
            if out.is_file() and out.stat().st_size > 1000:
                cached.append(self._rel(out))
            else:
                cached = []
                break
        if len(cached) == len(slices):
            return cached
        pngs: list[str] = []
        for idx in slices:
            png = export_slice_png(volume, slice_index=idx, out_dir=out_dir)
            pngs.append(self._rel(png))
        return pngs

    def _scan_volume_dir(
        self,
        root: Path,
        *,
        source: str,
        modality: str,
        study_prefix: str,
        title_fmt: str,
        collection: str = "",
    ) -> list[ImagingStudyItem]:
        items: list[ImagingStudyItem] = []
        if not root.exists():
            return items
        for case_dir in sorted(root.iterdir()):
            if not case_dir.is_dir() or case_dir.name.startswith("."):
                continue
            volume = case_dir / "imaging.nii.gz"
            if not volume.is_file():
                volume = next((p for p in case_dir.glob("*.nii.gz") if "seg" not in p.name.lower()), None)
            if volume is None:
                continue
            pngs = self._volume_previews(volume, case_dir.name)
            items.append(
                ImagingStudyItem(
                    study_id=f"{study_prefix}_{case_dir.name}",
                    patient_id=case_dir.name,
                    modality=modality,
                    source=source,
                    title=title_fmt.format(case=case_dir.name),
                    image_paths=pngs,
                    volume_path=self._rel(volume),
                    slice_count=len(pngs),
                    collection=collection,
                )
            )
        return items

    def _scan_mimic(self) -> list[ImagingStudyItem]:
        items: list[ImagingStudyItem] = []
        if not self.mimic_dir.exists():
            return items
        for patient_dir in sorted(self.mimic_dir.iterdir()):
            if not patient_dir.is_dir() or patient_dir.name.startswith("."):
                continue
            if is_mimic_cxr_jpg_patient(patient_dir.name):
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

    def _cxr_item_from_meta(self, key: str, meta: dict) -> ImagingStudyItem:
        patient_id = str(meta.get("patient_id", ""))
        collection = str(meta.get("collection", "") or infer_collection_label(patient_id))
        cxr_id = str(meta.get("cxr_id", "") or "")
        report_text = str(meta.get("report_text", "") or "")
        images = [str(p) for p in meta.get("image_paths") or []]
        title_bits = [f"CXR {patient_id}"]
        if collection:
            title_bits.append(f"({collection})")
        if cxr_id:
            title_bits.append(cxr_id)
        return ImagingStudyItem(
            study_id=key,
            patient_id=patient_id,
            modality="XR",
            source="mimic_cxr",
            title=" ".join(title_bits),
            image_paths=images,
            slice_count=len(images),
            collection=collection,
            report_text=report_text,
            cxr_id=cxr_id,
        )

    def _scan_mimic_cxr(self) -> list[ImagingStudyItem]:
        items: list[ImagingStudyItem] = []
        manifest_studies = self._cxr_manifest.get("studies") if isinstance(self._cxr_manifest, dict) else {}
        seen: set[str] = set()

        if isinstance(manifest_studies, dict):
            for key, meta in sorted(manifest_studies.items()):
                if not isinstance(meta, dict) or not meta.get("image_paths"):
                    continue
                items.append(self._cxr_item_from_meta(key, meta))
                seen.add(key)

        for root in (self.mimic_cxr_dir, self.mimic_dir):
            if not root.exists():
                continue
            for patient_dir in sorted(root.iterdir()):
                if not patient_dir.is_dir() or patient_dir.name.startswith("."):
                    continue
                if root is self.mimic_dir and not is_mimic_cxr_jpg_patient(patient_dir.name):
                    continue
                for study_dir in sorted(patient_dir.iterdir()):
                    if not study_dir.is_dir():
                        continue
                    if root is self.mimic_dir and not is_mimic_cxr_jpg_study(study_dir.name):
                        continue
                    key = study_key(patient_dir.name, study_dir.name)
                    if key in seen:
                        continue
                    images = sorted(
                        self._rel(p) for p in iter_study_images(study_dir)
                    )
                    if not images:
                        continue
                    report_text = ""
                    if root is self.mimic_dir:
                        report_text = load_mimic_cxr_jpg_report(patient_dir, study_dir.name)
                    collection = (
                        "MIMIC-CXR-JPG"
                        if root is self.mimic_dir
                        else infer_collection_label(patient_dir.name)
                    )
                    meta = {
                        "patient_id": patient_dir.name,
                        "collection": collection,
                        "cxr_id": "",
                        "report_text": report_text,
                        "image_paths": images,
                    }
                    items.append(self._cxr_item_from_meta(key, meta))
                    seen.add(key)
        return items

    def _scan_kits19(self) -> list[ImagingStudyItem]:
        return self._scan_volume_dir(
            self.kits19_dir,
            source="kits19",
            modality="CT",
            study_prefix="kits19",
            title_fmt="肾脏 CT · KiTS19 {case}",
            collection="KiTS19",
        )

    def _scan_chest_ct(self) -> list[ImagingStudyItem]:
        return self._scan_volume_dir(
            self.chest_ct_dir,
            source="chest_ct",
            modality="CT",
            study_prefix="chest_ct",
            title_fmt="胸部/肺 CT · {case}",
            collection="MONAI-COPD",
        )

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
            pngs = self._volume_previews(primary, case_dir.name)
            items.append(
                ImagingStudyItem(
                    study_id=f"brats_{case_dir.name}",
                    patient_id=case_dir.name,
                    modality="MRI",
                    source="brats2024",
                    title=f"脑 MRI · BraTS {case_dir.name}",
                    image_paths=pngs,
                    volume_path=self._rel(primary),
                    slice_count=len(pngs),
                    collection="BraTS",
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
    if is_mimic_cxr_jpg_patient(patient_id):
        return "MIMIC-CXR-JPG"
    return "local"
