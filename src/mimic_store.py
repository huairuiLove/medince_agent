"""Load and query MIMIC-III derived patient contexts from data/processed/."""
from __future__ import annotations

from pathlib import Path

from src.config import load_config, resolve_path
from src.schemas import MimicDataStatsResponse, MimicPatientListResponse, MimicPatientSummary, PatientContext
from src.utils import load_json

_REQUIRED_RAW_TABLES = (
    "PATIENTS.csv",
    "ADMISSIONS.csv",
    "PRESCRIPTIONS.csv",
    "DIAGNOSES_ICD.csv",
    "D_ICD_DIAGNOSES.csv",
    "NOTEEVENTS.csv",
    "LABEVENTS.csv",
    "ICUSTAYS.csv",
)


class MimicStore:
    def __init__(self) -> None:
        self._contexts: list[PatientContext] | None = None
        self._index: list[MimicPatientSummary] | None = None

    def raw_dir(self) -> Path:
        cfg = load_config()
        rel = cfg.get("data", {}).get("raw_dir", "data/mimic-iii-clinical-database-1.4")
        return resolve_path(rel)

    def contexts_path(self) -> Path:
        cfg = load_config()
        processed = resolve_path(cfg.get("data", {}).get("processed_dir", "data/processed"))
        return processed / "mimiciii_patient_contexts.json"

    def raw_table_status(self) -> dict[str, bool]:
        root = self.raw_dir()
        return {name: (root / name).is_file() for name in _REQUIRED_RAW_TABLES}

    def is_raw_available(self) -> bool:
        root = self.raw_dir()
        return (root / "PATIENTS.csv").is_file() and (root / "ADMISSIONS.csv").is_file()

    def is_processed_available(self) -> bool:
        path = self.contexts_path()
        return path.is_file() and path.stat().st_size > 1000

    def _load_contexts(self) -> list[PatientContext]:
        if self._contexts is not None:
            return self._contexts
        path = self.contexts_path()
        if not path.is_file():
            self._contexts = []
            return self._contexts
        raw = load_json(path)
        if not isinstance(raw, list):
            self._contexts = []
            return self._contexts
        self._contexts = [PatientContext.model_validate(item) for item in raw]
        return self._contexts

    def _build_index(self) -> list[MimicPatientSummary]:
        if self._index is not None:
            return self._index
        summaries: list[MimicPatientSummary] = []
        for ctx in self._load_contexts():
            if ctx.subject_id is None or ctx.hadm_id is None:
                continue
            summaries.append(
                MimicPatientSummary(
                    subject_id=ctx.subject_id,
                    hadm_id=ctx.hadm_id,
                    gender=ctx.gender,
                    age=ctx.age,
                    admission_type=ctx.admission_type,
                    diagnosis_count=len(ctx.diagnoses),
                    medication_count=len(ctx.current_medications),
                    has_chief_complaint=bool(ctx.chief_complaint.strip()),
                    has_allergies=bool(ctx.allergies),
                )
            )
        self._index = summaries
        return self._index

    def invalidate_cache(self) -> None:
        self._contexts = None
        self._index = None

    def stats(self) -> MimicDataStatsResponse:
        contexts = self._load_contexts()
        table_status = self.raw_table_status()
        with_notes = sum(1 for c in contexts if c.chief_complaint.strip())
        with_meds = sum(1 for c in contexts if c.current_medications)
        with_diag = sum(1 for c in contexts if c.diagnoses)
        ages = [c.age for c in contexts if c.age is not None]
        return MimicDataStatsResponse(
            raw_dir=str(self.raw_dir()),
            raw_available=self.is_raw_available(),
            raw_tables_present=sum(table_status.values()),
            raw_tables_required=len(_REQUIRED_RAW_TABLES),
            processed_path=str(self.contexts_path()),
            processed_available=self.is_processed_available(),
            context_count=len(contexts),
            with_clinical_notes=with_notes,
            with_medications=with_meds,
            with_diagnoses=with_diag,
            age_min=min(ages) if ages else None,
            age_max=max(ages) if ages else None,
        )

    def list_patients(
        self,
        *,
        offset: int = 0,
        limit: int = 25,
        gender: str | None = None,
        min_medications: int = 0,
    ) -> MimicPatientListResponse:
        items = self._build_index()
        if gender:
            g = gender.strip().upper()
            items = [item for item in items if item.gender.upper().startswith(g[:1])]
        if min_medications > 0:
            items = [item for item in items if item.medication_count >= min_medications]
        total = len(items)
        page = items[offset : offset + limit]
        return MimicPatientListResponse(total=total, offset=offset, limit=limit, items=page)

    def get_patient(self, subject_id: int, hadm_id: int) -> PatientContext | None:
        for ctx in self._load_contexts():
            if ctx.subject_id == subject_id and ctx.hadm_id == hadm_id:
                return ctx
        return None


_STORE: MimicStore | None = None


def get_mimic_store() -> MimicStore:
    global _STORE
    if _STORE is None:
        _STORE = MimicStore()
    return _STORE
