from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List

import pandas as pd
from tqdm import tqdm

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
ADMISSION_COLS = ["SUBJECT_ID", "HADM_ID", "ADMITTIME", "ADMISSION_TYPE"]
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


def read_csv(path: Path, usecols: Iterable[str]) -> pd.DataFrame:
    return pd.read_csv(path, usecols=list(usecols), low_memory=False)


def build_note_map(noteevents: pd.DataFrame) -> dict[tuple[int, int], str]:
    discharge_notes = noteevents[
        noteevents["CATEGORY"].astype(str).str.lower() == "discharge summary"
    ].copy()
    discharge_notes = discharge_notes.dropna(subset=["SUBJECT_ID", "HADM_ID"])

    for col in ("CHARTDATE", "CHARTTIME"):
        if col in discharge_notes.columns:
            discharge_notes[col] = pd.to_datetime(discharge_notes[col], errors="coerce")

    sort_cols = [col for col in ["SUBJECT_ID", "HADM_ID", "CHARTDATE", "CHARTTIME"] if col in discharge_notes.columns]
    if sort_cols:
        discharge_notes = discharge_notes.sort_values(sort_cols)

    discharge_notes = discharge_notes.drop_duplicates(["SUBJECT_ID", "HADM_ID"], keep="last")

    note_map: dict[tuple[int, int], str] = {}
    for _, row in discharge_notes.iterrows():
        key = (int(row["SUBJECT_ID"]), int(row["HADM_ID"]))
        note_map[key] = str(row.get("TEXT", "") or "")
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


def main(args: argparse.Namespace) -> None:
    raw_dir = Path(args.raw_dir)
    out_path = Path(args.out_path)

    patients = read_csv(raw_dir / "PATIENTS.csv", PATIENT_COLS)
    admissions = read_csv(raw_dir / "ADMISSIONS.csv", ADMISSION_COLS)
    diagnoses = read_csv(raw_dir / "DIAGNOSES_ICD.csv", DIAGNOSIS_COLS)
    d_icd = read_csv(raw_dir / "D_ICD_DIAGNOSES.csv", D_ICD_COLS)
    prescriptions = read_csv(raw_dir / "PRESCRIPTIONS.csv", PRESCRIPTION_COLS)
    noteevents = read_csv(raw_dir / "NOTEEVENTS.csv", NOTEEVENT_COLS)

    patients["DOB"] = pd.to_datetime(patients["DOB"], errors="coerce")
    admissions["ADMITTIME"] = pd.to_datetime(admissions["ADMITTIME"], errors="coerce")

    note_map = build_note_map(noteevents)
    diag_group = build_diagnosis_map(diagnoses, d_icd)
    med_group = build_medication_map(prescriptions)

    merged = admissions.merge(patients, on="SUBJECT_ID", how="left")

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

        sample = PatientContext(
            subject_id=sid,
            hadm_id=hadm,
            gender=gender,
            age=age,
            admission_type=admission_type,
            chief_complaint=chief,
            history_present_illness=hpi,
            past_medical_history=pmh[:10],
            diagnoses=diag_group.get(key, [])[:10],
            current_medications=med_group.get(key, [])[:20],
            allergies=allergies[:10],
            pregnancy_status=infer_pregnancy_status(gender, note_text),
            missing_fields=dedupe_preserve_order(missing_fields),
        )
        samples.append(sample.model_dump())

        if args.max_samples > 0 and len(samples) >= args.max_samples:
            break

    save_json(samples, out_path)
    print(f"saved {len(samples)} samples to {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build patient-context samples from MIMIC-III.")
    parser.add_argument("--raw_dir", type=str, required=True)
    parser.add_argument("--out_path", type=str, required=True)
    parser.add_argument("--max_samples", type=int, default=2000)
    main(parser.parse_args())
