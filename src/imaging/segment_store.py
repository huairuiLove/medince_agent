"""Persist segmentation runs and overlay artifacts locally."""
from __future__ import annotations

import shutil
from pathlib import Path

from src.config import resolve_path
from src.schemas import SegmentRunRecord
from src.utils import ensure_dir, load_json, make_case_id, save_json, utc_now_iso


def make_image_key(
    image_path: str,
    volume_path: str | None = None,
    slice_axis: str = "axial",
    slice_index: int | None = None,
) -> str:
    vol = volume_path or ""
    if vol and (image_path == vol or str(image_path).endswith((".nii.gz", ".nii"))):
        return f"vol:{vol}|{slice_axis}|{slice_index if slice_index is not None else 0}"
    root = resolve_path(".")
    try:
        rel = str(Path(image_path).resolve().relative_to(root.resolve()))
    except ValueError:
        rel = image_path
    return f"img:{rel}"


class SegmentStore:
    def __init__(self, base_dir: str | Path | None = None) -> None:
        self.base_dir = Path(base_dir) if base_dir else resolve_path("data/imaging_cache/segments")
        ensure_dir(self.base_dir)

    def _study_dir(self, patient_id: str, study_id: str) -> Path:
        d = self.base_dir / patient_id / study_id
        ensure_dir(d)
        return d

    def _run_dir(self, patient_id: str, study_id: str, run_id: str) -> Path:
        d = self._study_dir(patient_id, study_id) / run_id
        ensure_dir(d)
        return d

    def save_run(
        self,
        patient_id: str,
        study_id: str,
        image_key: str,
        source_image: str,
        volume_path: str | None,
        slice_axis: str,
        slice_index: int | None,
        organ: str,
        model_ids: list[str],
        results: list[dict],
        memory_peak_mb: float,
    ) -> SegmentRunRecord:
        run_id = make_case_id("seg")
        run_dir = self._run_dir(patient_id, study_id, run_id)
        root = resolve_path(".")

        persisted_results: list[dict] = []
        for r in results:
            item = dict(r)
            src_overlay = Path(item["overlay_path"])
            if src_overlay.exists():
                dest = run_dir / f"{item['model_id']}_overlay.png"
                shutil.copy2(src_overlay, dest)
                item["overlay_path"] = str(dest.relative_to(root))

            stats = dict(item.get("stats") or {})
            mask_path = stats.get("volume_mask_path")
            if mask_path and isinstance(mask_path, str):
                mp = Path(mask_path)
                if not mp.is_absolute():
                    mp = root / mask_path
                if mp.exists():
                    suffix = mp.suffix
                    if str(mp).endswith(".nii.gz"):
                        suffix = ".nii.gz"
                    dest_mask = run_dir / f"{item['model_id']}_mask{suffix}"
                    shutil.copy2(mp, dest_mask)
                    stats["volume_mask_path"] = str(dest_mask.relative_to(root))
            item["stats"] = stats
            persisted_results.append(item)

        record = SegmentRunRecord(
            run_id=run_id,
            patient_id=patient_id,
            study_id=study_id,
            image_key=image_key,
            source_image=source_image,
            volume_path=volume_path,
            slice_axis=slice_axis,
            slice_index=slice_index,
            organ=organ,
            model_ids=model_ids,
            results=persisted_results,
            memory_peak_mb=memory_peak_mb,
            created_at=utc_now_iso(),
        )
        save_json(record.model_dump(), self._study_dir(patient_id, study_id) / f"{run_id}.json")
        return record

    def list_runs(
        self,
        patient_id: str,
        study_id: str,
        image_key: str | None = None,
    ) -> list[SegmentRunRecord]:
        study_dir = self._study_dir(patient_id, study_id)
        if not study_dir.exists():
            return []
        runs: list[SegmentRunRecord] = []
        for fp in sorted(study_dir.glob("seg_*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            record = SegmentRunRecord.model_validate(load_json(fp))
            if image_key is None or record.image_key == image_key:
                runs.append(record)
        return runs
