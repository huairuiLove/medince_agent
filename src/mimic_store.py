"""Load and query MIMIC-III derived patient contexts from datasets/processed/."""
from __future__ import annotations

from pathlib import Path

from src.config import load_config, resolve_path
from src.imaging.catalog import ImagingCatalog
from src.mimic_io import cxr_patient_folder, resolve_table_path, table_exists
from src.schemas import MimicDataStatsResponse, MimicPatientListResponse, MimicPatientSummary, PatientContext
from src.utils import load_json

_RAW_TABLE_BASES = (
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
        self._search_blob: dict[tuple[int, int], str] | None = None

    def raw_dir(self) -> Path:
        cfg = load_config()
        rel = cfg.get("data", {}).get("raw_dir", "datasets/mimic-iii-clinical-database-1.4")
        return resolve_path(rel)

    def contexts_path(self) -> Path:
        cfg = load_config()
        processed = resolve_path(cfg.get("data", {}).get("processed_dir", "datasets/processed"))
        return processed / "mimiciii_patient_contexts.json"

    def raw_table_status(self) -> dict[str, bool]:
        root = self.raw_dir()
        return {name: table_exists(root, name) for name in _RAW_TABLE_BASES}

    def is_raw_available(self) -> bool:
        root = self.raw_dir()
        return table_exists(root, "PATIENTS.csv") and table_exists(root, "ADMISSIONS.csv")

    def is_processed_available(self) -> bool:
        path = self.contexts_path()
        return path.is_file() and path.stat().st_size > 1000

    def dataset_tier(self) -> str:
        root = self.raw_dir()
        rx = resolve_table_path(root, "PRESCRIPTIONS.csv")
        if rx is None:
            return "missing"
        if rx.stat().st_size >= 50_000_000:
            return "full"
        return "demo"

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

    def _search_text(self, ctx: PatientContext) -> str:
        parts = [
            ctx.chief_complaint,
            ctx.history_present_illness,
            ctx.admission_type,
            " ".join(ctx.allergies),
            " ".join(d.name for d in ctx.diagnoses),
            " ".join(m.name for m in ctx.current_medications),
        ]
        return " ".join(p.lower() for p in parts if p)

    def _build_index(self) -> list[MimicPatientSummary]:
        if self._index is not None:
            return self._index
        summaries: list[MimicPatientSummary] = []
        blobs: dict[tuple[int, int], str] = {}
        for ctx in self._load_contexts():
            if ctx.subject_id is None or ctx.hadm_id is None:
                continue
            key = (ctx.subject_id, ctx.hadm_id)
            primary_dx = ctx.diagnoses[0].name if ctx.diagnoses else ""
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
                    icu_stay=ctx.icu_stay,
                    has_imaging=ctx.has_imaging,
                    egfr=ctx.egfr,
                    primary_diagnosis=primary_dx,
                )
            )
            blobs[key] = self._search_text(ctx)
        self._search_blob = blobs
        self._index = summaries
        return self._index

    def invalidate_cache(self) -> None:
        self._contexts = None
        self._index = None
        self._search_blob = None

    def stats(self) -> MimicDataStatsResponse:
        contexts = self._load_contexts()
        table_status = self.raw_table_status()
        with_notes = sum(1 for c in contexts if c.chief_complaint.strip())
        with_meds = sum(1 for c in contexts if c.current_medications)
        with_diag = sum(1 for c in contexts if c.diagnoses)
        with_labs = sum(1 for c in contexts if c.labs)
        with_icu = sum(1 for c in contexts if c.icu_stay)
        with_imaging = sum(1 for c in contexts if c.has_imaging)
        ages = [c.age for c in contexts if c.age is not None]
        return MimicDataStatsResponse(
            raw_dir=str(self.raw_dir()),
            raw_available=self.is_raw_available(),
            raw_tables_present=sum(table_status.values()),
            raw_tables_required=len(_RAW_TABLE_BASES),
            processed_path=str(self.contexts_path()),
            processed_available=self.is_processed_available(),
            context_count=len(contexts),
            with_clinical_notes=with_notes,
            with_medications=with_meds,
            with_diagnoses=with_diag,
            with_labs=with_labs,
            with_icu=with_icu,
            with_imaging=with_imaging,
            age_min=min(ages) if ages else None,
            age_max=max(ages) if ages else None,
            dataset_tier=self.dataset_tier(),
        )

    def list_patients(
        self,
        *,
        offset: int = 0,
        limit: int = 25,
        gender: str | None = None,
        min_medications: int = 0,
        q: str | None = None,
        icu_only: bool = False,
        has_imaging: bool | None = None,
        min_age: int | None = None,
        max_age: int | None = None,
        admission_type: str | None = None,
    ) -> MimicPatientListResponse:
        items = self._build_index()
        if self._search_blob is None:
            self._build_index()

        filtered: list[MimicPatientSummary] = []
        query = (q or "").strip().lower()
        adm_filter = (admission_type or "").strip().upper()

        for item in items:
            if gender:
                g = gender.strip().upper()
                if not item.gender.upper().startswith(g[:1]):
                    continue
            if min_medications > 0 and item.medication_count < min_medications:
                continue
            if icu_only and not item.icu_stay:
                continue
            if has_imaging is True and not item.has_imaging:
                continue
            if has_imaging is False and item.has_imaging:
                continue
            if min_age is not None and (item.age is None or item.age < min_age):
                continue
            if max_age is not None and (item.age is None or item.age > max_age):
                continue
            if adm_filter and adm_filter not in (item.admission_type or "").upper():
                continue
            if query:
                blob = self._search_blob.get((item.subject_id, item.hadm_id), "")
                if query not in blob and query not in str(item.subject_id):
                    continue
            filtered.append(item)

        total = len(filtered)
        page = filtered[offset : offset + limit]
        return MimicPatientListResponse(total=total, offset=offset, limit=limit, items=page)

    def get_patient(self, subject_id: int, hadm_id: int) -> PatientContext | None:
        for ctx in self._load_contexts():
            if ctx.subject_id == subject_id and ctx.hadm_id == hadm_id:
                return ctx
        return None

    def list_imaging_studies(self, subject_id: int) -> list:
        catalog = ImagingCatalog()
        patient_folder = cxr_patient_folder(subject_id)
        studies = catalog.list_studies(source="mimic_cxr")
        return [s for s in studies if s.patient_id == patient_folder]


_STORE: MimicStore | None = None


def get_mimic_store() -> MimicStore:
    global _STORE
    if _STORE is None:
        _STORE = MimicStore()
    return _STORE
