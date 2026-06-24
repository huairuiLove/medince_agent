"""Resolve MIMIC-III CSV / CSV.GZ tables and shared I/O helpers."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd


def resolve_table_path(raw_dir: Path, base_name: str) -> Path | None:
    """Prefer .csv.gz (smaller) when both exist; fall back to .csv."""
    gz = raw_dir / f"{base_name}.gz"
    plain = raw_dir / base_name
    if gz.is_file():
        return gz
    if plain.is_file():
        return plain
    return None


def table_exists(raw_dir: Path, base_name: str) -> bool:
    return resolve_table_path(raw_dir, base_name) is not None


def read_table(
    raw_dir: Path,
    base_name: str,
    usecols: Iterable[str],
    *,
    chunksize: int | None = None,
):
    path = resolve_table_path(raw_dir, base_name)
    if path is None:
        raise FileNotFoundError(f"{base_name} not found under {raw_dir}")
    compression = "gzip" if path.suffix == ".gz" else None
    return pd.read_csv(
        path,
        usecols=list(usecols),
        low_memory=False,
        compression=compression,
        chunksize=chunksize,
    )


def cxr_patient_folder(subject_id: int) -> str:
    """MIMIC-CXR-JPG patient directory name for a MIMIC-III SUBJECT_ID."""
    return f"p{int(subject_id):08d}"


def estimate_egfr_mg_dl(
    creatinine_mg_dl: float,
    age: int,
    gender: str,
    *,
    is_black: bool = False,
) -> float | None:
    """MDRD-style eGFR estimate (mL/min/1.73m²). Returns None if inputs invalid."""
    if creatinine_mg_dl <= 0 or age <= 0:
        return None
    female = str(gender).upper().startswith("F")
    egfr = 175.0 * (creatinine_mg_dl ** -1.154) * (age ** -0.203)
    if female:
        egfr *= 0.742
    if is_black:
        egfr *= 1.212
    return round(max(egfr, 0.0), 1)
