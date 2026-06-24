"""Per-study Qwen VLM + DeepSeek analysis cache (source images only, no overlays)."""
from __future__ import annotations

from pathlib import Path

from src.config import resolve_path
from src.schemas import ImagingAnalysisCacheEntry
from src.utils import ensure_dir, load_json, save_json, utc_now_iso


class ImagingAnalysisCacheStore:
    def __init__(self, base_dir: str | Path | None = None) -> None:
        self.base_dir = Path(base_dir) if base_dir else resolve_path("data/imaging_cache/analysis")
        ensure_dir(self.base_dir)

    def _path(self, source: str, patient_id: str, study_id: str) -> Path:
        safe_source = (source or "unknown").strip().replace("/", "_")
        d = self.base_dir / safe_source / patient_id
        ensure_dir(d)
        return d / f"{study_id}.json"

    def get(self, source: str, patient_id: str, study_id: str) -> ImagingAnalysisCacheEntry | None:
        path = self._path(source, patient_id, study_id)
        if not path.exists():
            return None
        return ImagingAnalysisCacheEntry.model_validate(load_json(path))

    def save(self, entry: ImagingAnalysisCacheEntry) -> ImagingAnalysisCacheEntry:
        now = utc_now_iso()
        if not entry.created_at:
            entry.created_at = now
        entry.updated_at = now
        save_json(entry.model_dump(), self._path(entry.source, entry.patient_id, entry.study_id))
        return entry

    def list_cached_study_ids(self, source: str | None = None) -> list[tuple[str, str, str]]:
        out: list[tuple[str, str, str]] = []
        if not self.base_dir.exists():
            return out
        for src_dir in sorted(self.base_dir.iterdir()):
            if not src_dir.is_dir():
                continue
            if source and src_dir.name != source.replace("/", "_"):
                continue
            for patient_dir in src_dir.iterdir():
                if not patient_dir.is_dir():
                    continue
                for fp in patient_dir.glob("*.json"):
                    out.append((src_dir.name, patient_dir.name, fp.stem))
        return out
