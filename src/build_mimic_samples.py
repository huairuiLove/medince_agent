from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Set

import pandas as pd
from tqdm import tqdm

from src.imaging.cxr_manifest import is_mimic_cxr_jpg_patient, load_manifest
from src.mimic_io import cxr_patient_folder, estimate_egfr_mg_dl, read_table, resolve_table_path, table_exists
from src.schemas import DiagnosisItem, DrugItem, PatientContext
from src.utils import dedupe_preserve_order, save_json


SECTION_PATTERNS = {
    "chief_complaint": re.compile(
        r"(?:chief complaint|reason for admission)\s*:(.*?)(?:\n\s*[A-Z][A-Z0-9 /_-]{2,}\s*:|$)",
        re.I | re.S,
    ),
    "history_present_illness": re.compile(
        r"(?:history of present illness|history present illness|hpi)\s*:(.*?)(?:\n\s*[A-Z][A-Z0-9 /_-]{2,}\s*:|$)",
        re.I | re.S,
    ),
    "past_medical_history": re.compile(
        r"(?:past medical history|pmh)\s*:(.*?)(?:\n\s*[A-Z][A-Z0-9 /_-]{2,}\s*:|$)",
        re.I | re.S,
    ),
    "allergies": re.compile(
        r"allergies\s*:(.*?)(?:\n\s*[A-Z][A-Z0-9 /_-]{2,}\s*:|$)",
        re.I | re.S,
    ),
}

PATIENT_COLS = ["SUBJECT_ID", "GENDER", "DOB"]
ADMISSION_COLS = ["SUBJECT_ID", "HADM_ID", "ADMITTIME", "ADMISSION_TYPE", "ETHNICITY"]
DIAGNOSIS_COLS = ["SUBJECT_ID", "HADM_ID", "ICD9_CODE"]
D_ICD_COLS = ["ICD9_CODE", "SHORT_TITLE"]
PRESCRIPTION_COLS = [
    "SUBJECT_ID",
    "HADM_ID",
    "DRUG",
    "DOSE_VAL_RX",
    "DOSE_UNIT_RX",
    "ROUTE",
]
NOTEEVENT_COLS = ["SUBJECT_ID", "HADM_ID", "CATEGORY", "CHARTDATE", "CHARTTIME", "TEXT"]
ICUSTAY_COLS = ["SUBJECT_ID", "HADM_ID"]
LABEVENT_COLS = ["SUBJECT_ID", "HADM_ID", "ITEMID", "CHARTTIME", "VALUENUM"]

# MIMIC-III D_LABITEMS common chemistry / coagulation itemids
LAB_ITEM_MAP: dict[int, str] = {
    50912: "creatinine_mg_dl",
    50971: "potassium_meq_l",
    51237: "inr",
    50931: "glucose_mg_dl",
    51006: "bun_mg_dl",
    51222: "hemoglobin_g_dl",
    50983: "sodium_meq_l",
    50813: "lactate_mmol_l",
}


def clean_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    cleaned = text.replace("\r", "\n")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{2,}", "\n", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def extract_section(text: str, key: str) -> str:
    if not isinstance(text, str):
        return ""
    match = SECTION_PATTERNS[key].search(text)
    if not match:
        return ""
    return clean_text(match.group(1))


def split_section_items(text: str) -> list[str]:
    if not text:
        return []
    pieces = re.split(r"[;\n]|(?:\s{2,})", text)
    return dedupe_preserve_order(piece.strip(" -") for piece in pieces)


def compute_age(admittime: pd.Timestamp, dob: pd.Timestamp) -> int | None:
    if pd.isna(admittime) or pd.isna(dob):
        return None
    age = admittime.year - dob.year - ((admittime.month, admittime.day) < (dob.month, dob.day))
    if age < 0:
        return None
    if age > 120:
        return 90
    return int(age)


def infer_pregnancy_status(gender: str, note_text: str) -> str:
    if gender.upper() not in {"F", "FEMALE"}:
        return "unknown"

    text = note_text.lower()
    negative_patterns = [
        r"denies pregnancy",
        r"negative pregnancy",
        r"not pregnant",
        r"pregnancy test negative",
    ]
    positive_patterns = [r"\bpregnant\b", r"pregnancy", r"gestation"]

    if any(re.search(pattern, text) for pattern in negative_patterns):
        return "not pregnant"
    if any(re.search(pattern, text) for pattern in positive_patterns):
        return "pregnant"
    return "unknown"


def is_black_ethnicity(ethnicity: str) -> bool:
    text = (ethnicity or "").upper()
    return "BLACK" in text or "AFRICAN" in text


def build_note_map_from_path(path: Path, *, chunk_size: int = 50_000) -> dict[tuple[int, int], str]:
    """Stream NOTEEVENTS and keep the latest discharge summary per admission."""
    note_map: dict[tuple[int, int], str] = {}
    sort_meta: dict[tuple[int, int], tuple] = {}

    compression = "gzip" if path.suffix == ".gz" else None
    reader = pd.read_csv(
        path,
        usecols=list(NOTEEVENT_COLS),
        chunksize=chunk_size,
        low_memory=False,
        compression=compression,
    )
    for chunk in tqdm(reader, desc="Reading discharge summaries"):
        discharge = chunk[
            chunk["CATEGORY"].astype(str).str.lower() == "discharge summary"
        ].dropna(subset=["SUBJECT_ID", "HADM_ID"])
        if discharge.empty:
            continue

        for col in ("CHARTDATE", "CHARTTIME"):
            if col in discharge.columns:
                discharge[col] = pd.to_datetime(discharge[col], errors="coerce")

        for _, row in discharge.iterrows():
            key = (int(row["SUBJECT_ID"]), int(row["HADM_ID"]))
            chartdate = row.get("CHARTDATE")
            charttime = row.get("CHARTTIME")
            meta = (
                chartdate if not pd.isna(chartdate) else pd.Timestamp.min,
                charttime if not pd.isna(charttime) else pd.Timestamp.min,
            )
            if key not in note_map or meta >= sort_meta.get(key, (pd.Timestamp.min, pd.Timestamp.min)):
                note_map[key] = str(row.get("TEXT", "") or "")
                sort_meta[key] = meta

    return note_map


def build_diagnosis_map(diagnoses: pd.DataFrame, d_icd: pd.DataFrame) -> Dict[tuple[int, int], List[DiagnosisItem]]:
    diag_map = d_icd[["ICD9_CODE", "SHORT_TITLE"]].drop_duplicates()
    diag_name_map = dict(zip(diag_map["ICD9_CODE"].astype(str), diag_map["SHORT_TITLE"].astype(str)))

    grouped: Dict[tuple[int, int], List[DiagnosisItem]] = defaultdict(list)
    for _, row in diagnoses.iterrows():
        sid = row.get("SUBJECT_ID")
        hadm = row.get("HADM_ID")
        code = str(row.get("ICD9_CODE", "") or "")
        if pd.isna(sid) or pd.isna(hadm) or not code:
            continue

        item = DiagnosisItem(icd9_code=code, name=diag_name_map.get(code, ""))
        key = (int(sid), int(hadm))

        if item not in grouped[key]:
            grouped[key].append(item)

    return grouped


def build_medication_map(prescriptions: pd.DataFrame) -> Dict[tuple[int, int], List[DrugItem]]:
    grouped: Dict[tuple[int, int], List[DrugItem]] = defaultdict(list)
    for _, row in prescriptions.iterrows():
        sid = row.get("SUBJECT_ID")
        hadm = row.get("HADM_ID")
        if pd.isna(sid) or pd.isna(hadm):
            continue

        dose_val = str(row.get("DOSE_VAL_RX", "") or "").strip()
        dose_unit = str(row.get("DOSE_UNIT_RX", "") or "").strip()
        dose = " ".join(part for part in [dose_val, dose_unit] if part).strip()

        item = DrugItem(
            name=str(row.get("DRUG", "") or "").strip(),
            dose=dose,
            route=str(row.get("ROUTE", "") or "").strip(),
            frequency="",
        )
        if not item.name:
            continue

        key = (int(sid), int(hadm))
        if item not in grouped[key]:
            grouped[key].append(item)

    return grouped


def build_icu_admission_set(raw_dir: Path) -> Set[tuple[int, int]]:
    if not table_exists(raw_dir, "ICUSTAYS.csv"):
        return set()
    icustays = read_table(raw_dir, "ICUSTAYS.csv", ICUSTAY_COLS)
    icustays = icustays.dropna(subset=["SUBJECT_ID", "HADM_ID"])
    return {
        (int(row["SUBJECT_ID"]), int(row["HADM_ID"]))
        for _, row in icustays.iterrows()
    }


def build_lab_map(
    raw_dir: Path,
    target_keys: Set[tuple[int, int]],
    *,
    chunk_size: int = 200_000,
) -> dict[tuple[int, int], dict[str, float]]:
    """Latest lab value per admission for selected ITEMIDs."""
    if not target_keys or not table_exists(raw_dir, "LABEVENTS.csv"):
        return {}

    item_ids = set(LAB_ITEM_MAP.keys())
    lab_map: dict[tuple[int, int], dict[str, float]] = {}
    sort_meta: dict[tuple[int, int], dict[str, pd.Timestamp]] = defaultdict(dict)

    reader = read_table(raw_dir, "LABEVENTS.csv", LABEVENT_COLS, chunksize=chunk_size)
    for chunk in tqdm(reader, desc="Reading lab events"):
        chunk = chunk.dropna(subset=["SUBJECT_ID", "HADM_ID", "ITEMID", "VALUENUM"])
        chunk = chunk[chunk["ITEMID"].isin(item_ids)]
        if chunk.empty:
            continue
        chunk["CHARTTIME"] = pd.to_datetime(chunk["CHARTTIME"], errors="coerce")

        for _, row in chunk.iterrows():
            key = (int(row["SUBJECT_ID"]), int(row["HADM_ID"]))
            if key not in target_keys:
                continue
            item_id = int(row["ITEMID"])
            field = LAB_ITEM_MAP.get(item_id)
            if not field:
                continue
            value = float(row["VALUENUM"])
            charttime = row.get("CHARTTIME")
            if pd.isna(charttime):
                charttime = pd.Timestamp.min
            prev_time = sort_meta[key].get(field, pd.Timestamp.min)
            if field not in lab_map.get(key, {}) or charttime >= prev_time:
                lab_map.setdefault(key, {})[field] = value
                sort_meta[key][field] = charttime

    return lab_map


def load_cxr_patient_index() -> Set[str]:
    """Patient folder IDs (p########) with indexed CXR studies on disk."""
    indexed: Set[str] = set()
    manifest = load_manifest()
    studies = manifest.get("studies") or {}
    if isinstance(studies, dict):
        for study in studies.values():
            if not isinstance(study, dict):
                continue
            patient_id = str(study.get("patient_id", "") or "")
            if is_mimic_cxr_jpg_patient(patient_id):
                indexed.add(patient_id)
    from src.config import datasets_path

    root = datasets_path("mimic")
    if root.is_dir():
        for patient_dir in root.iterdir():
            if patient_dir.is_dir() and is_mimic_cxr_jpg_patient(patient_dir.name):
                indexed.add(patient_dir.name)
    return indexed


def note_excerpt(note_text: str, limit: int = 2000) -> str:
    text = clean_text(note_text)
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def main(args: argparse.Namespace) -> None:
    raw_dir = Path(args.raw_dir)
    out_path = Path(args.out_path)

    patients = read_table(raw_dir, "PATIENTS.csv", PATIENT_COLS)
    admissions = read_table(raw_dir, "ADMISSIONS.csv", ADMISSION_COLS)
    diagnoses = read_table(raw_dir, "DIAGNOSES_ICD.csv", DIAGNOSIS_COLS)
    d_icd = read_table(raw_dir, "D_ICD_DIAGNOSES.csv", D_ICD_COLS)
    prescriptions = read_table(raw_dir, "PRESCRIPTIONS.csv", PRESCRIPTION_COLS)

    note_map: dict[tuple[int, int], str] = {}
    if not args.skip_notes:
        notes_path = resolve_table_path(raw_dir, "NOTEEVENTS.csv")
        if notes_path is None:
            print("WARNING: NOTEEVENTS not found; continuing without clinical notes.")
        else:
            print(f"Loading discharge summaries from {notes_path.name} ...")
            note_map = build_note_map_from_path(notes_path, chunk_size=args.note_chunk_size)

    icu_set = build_icu_admission_set(raw_dir) if args.include_icu else set()
    cxr_patients = load_cxr_patient_index() if args.include_imaging else set()

    patients["DOB"] = pd.to_datetime(patients["DOB"], errors="coerce")
    admissions["ADMITTIME"] = pd.to_datetime(admissions["ADMITTIME"], errors="coerce")

    diag_group = build_diagnosis_map(diagnoses, d_icd)
    med_group = build_medication_map(prescriptions)

    merged = admissions.merge(patients, on="SUBJECT_ID", how="left")
    if args.require_medications:
        merged = merged[
            merged.apply(
                lambda row: bool(med_group.get((int(row["SUBJECT_ID"]), int(row["HADM_ID"]))))
                if not pd.isna(row.get("HADM_ID")) and not pd.isna(row.get("SUBJECT_ID"))
                else False,
                axis=1,
            )
        ]

    admission_keys: Set[tuple[int, int]] = set()
    for _, row in merged.iterrows():
        if pd.isna(row.get("HADM_ID")) or pd.isna(row.get("SUBJECT_ID")):
            continue
        admission_keys.add((int(row["SUBJECT_ID"]), int(row["HADM_ID"])))

    lab_group: dict[tuple[int, int], dict[str, float]] = {}
    if args.include_labs and admission_keys:
        print(f"Loading labs for {len(admission_keys):,} admissions ...")
        lab_group = build_lab_map(raw_dir, admission_keys, chunk_size=args.lab_chunk_size)

    samples: list[dict] = []
    for _, row in tqdm(merged.iterrows(), total=len(merged), desc="Building patient contexts"):
        if pd.isna(row.get("HADM_ID")) or pd.isna(row.get("SUBJECT_ID")):
            continue

        sid = int(row["SUBJECT_ID"])
        hadm = int(row["HADM_ID"])
        key = (sid, hadm)
        note_text = note_map.get(key, "")

        chief = extract_section(note_text, "chief_complaint")
        hpi = extract_section(note_text, "history_present_illness")
        pmh = split_section_items(extract_section(note_text, "past_medical_history"))
        allergies = split_section_items(extract_section(note_text, "allergies"))
        age = compute_age(row.get("ADMITTIME"), row.get("DOB"))
        gender = str(row.get("GENDER", "unknown") or "unknown").strip()
        admission_type = str(row.get("ADMISSION_TYPE", "") or "").strip()
        labs = lab_group.get(key, {})
        creatinine = labs.get("creatinine_mg_dl")
        ethnicity = str(row.get("ETHNICITY", "") or "")
        egfr = None
        if creatinine is not None and age is not None:
            egfr = estimate_egfr_mg_dl(
                creatinine,
                age,
                gender,
                is_black=is_black_ethnicity(ethnicity),
            )

        missing_fields: list[str] = []
        if not chief:
            missing_fields.append("chief_complaint")
        if not hpi:
            missing_fields.append("history_present_illness")
        if age is None:
            missing_fields.append("age")
        if not allergies:
            missing_fields.append("allergies")
        if not med_group.get(key):
            missing_fields.append("current_medications")
        if egfr is None:
            missing_fields.append("egfr")

        sample = PatientContext(
            subject_id=sid,
            hadm_id=hadm,
            gender=gender,
            age=age,
            admission_type=admission_type,
            source_text=note_excerpt(note_text),
            chief_complaint=chief,
            history_present_illness=hpi,
            past_medical_history=pmh[:10],
            diagnoses=diag_group.get(key, [])[:10],
            current_medications=med_group.get(key, [])[:20],
            allergies=allergies[:10],
            pregnancy_status=infer_pregnancy_status(gender, note_text),
            labs=labs,
            egfr=egfr,
            icu_stay=key in icu_set,
            has_imaging=cxr_patient_folder(sid) in cxr_patients,
            missing_fields=dedupe_preserve_order(missing_fields),
        )
        samples.append(sample.model_dump())

        if args.max_samples > 0 and len(samples) >= args.max_samples:
            break

    save_json(samples, out_path)
    with_labs = sum(1 for s in samples if s.get("labs"))
    with_notes = sum(1 for s in samples if s.get("chief_complaint"))
    with_icu = sum(1 for s in samples if s.get("icu_stay"))
    with_imaging = sum(1 for s in samples if s.get("has_imaging"))
    print(f"saved {len(samples)} samples to {out_path}")
    print(f"  with clinical notes: {with_notes}")
    print(f"  with labs: {with_labs}")
    print(f"  with ICU stay: {with_icu}")
    print(f"  with CXR on disk: {with_imaging}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build patient-context samples from MIMIC-III.")
    parser.add_argument("--raw_dir", type=str, required=True)
    parser.add_argument("--out_path", type=str, required=True)
    parser.add_argument(
        "--max_samples",
        type=int,
        default=0,
        help="Max admissions to export (0 = all matching filters).",
    )
    parser.add_argument(
        "--skip-notes",
        action="store_true",
        help="Skip NOTEEVENTS (faster; chief complaint / HPI / allergies will be empty).",
    )
    parser.add_argument(
        "--require-medications",
        action="store_true",
        help="Only include admissions with at least one prescription.",
    )
    parser.add_argument(
        "--include-labs",
        action="store_true",
        default=True,
        help="Include LABEVENTS chemistry/coagulation values (default: on).",
    )
    parser.add_argument(
        "--no-labs",
        action="store_true",
        help="Skip LABEVENTS (faster build).",
    )
    parser.add_argument(
        "--include-icu",
        action="store_true",
        default=True,
        help="Mark ICU admissions from ICUSTAYS.csv (default: on).",
    )
    parser.add_argument(
        "--include-imaging",
        action="store_true",
        default=True,
        help="Set has_imaging when MIMIC-CXR-JPG folder exists (default: on).",
    )
    parser.add_argument(
        "--note-chunk-size",
        type=int,
        default=50_000,
        help="Chunk size when streaming NOTEEVENTS.",
    )
    parser.add_argument(
        "--lab-chunk-size",
        type=int,
        default=200_000,
        help="Chunk size when streaming LABEVENTS.",
    )
    ns = parser.parse_args()
    if ns.no_labs:
        ns.include_labs = False
    main(ns)
