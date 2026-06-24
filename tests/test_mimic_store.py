"""Tests for MIMIC-III store and I/O helpers."""
from __future__ import annotations

from src.mimic_io import cxr_patient_folder, estimate_egfr_mg_dl, table_exists
from src.mimic_store import MimicStore
from src.schemas import PatientContext


def test_cxr_patient_folder():
    assert cxr_patient_folder(10000980) == "p10000980"


def test_estimate_egfr():
    egfr = estimate_egfr_mg_dl(1.0, 60, "M")
    assert egfr is not None
    assert egfr > 50


def test_mimic_store_list_with_filters(tmp_path, monkeypatch):
    processed = tmp_path / "processed"
    processed.mkdir()
    sample = PatientContext(
        subject_id=100,
        hadm_id=200,
        gender="M",
        age=72,
        admission_type="EMERGENCY",
        chief_complaint="chest pain",
        diagnoses=[{"name": "pneumonia", "icd9_code": "486"}],
        current_medications=[{"name": "warfarin"}],
        icu_stay=True,
        has_imaging=True,
        egfr=45.0,
    ).model_dump()
    (processed / "mimiciii_patient_contexts.json").write_text(
        __import__("json").dumps([sample]),
        encoding="utf-8",
    )

    store = MimicStore()
    monkeypatch.setattr(store, "contexts_path", lambda: processed / "mimiciii_patient_contexts.json")
    monkeypatch.setattr(store, "is_processed_available", lambda: True)
    store.invalidate_cache()

    all_items = store.list_patients(limit=10)
    assert all_items.total == 1

    icu = store.list_patients(icu_only=True, limit=10)
    assert icu.total == 1

    none = store.list_patients(q="diabetes", limit=10)
    assert none.total == 0

    hit = store.list_patients(q="pneumonia", limit=10)
    assert hit.total == 1


def test_raw_table_exists_for_full_dataset():
    store = MimicStore()
    if not store.raw_dir().is_dir():
        return
    assert table_exists(store.raw_dir(), "PATIENTS.csv")
    assert table_exists(store.raw_dir(), "ADMISSIONS.csv")
