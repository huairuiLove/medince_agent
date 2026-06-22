"""FHIR terminology mappings: RxNorm, LOINC, SNOMED, ActCode, ATC."""

from __future__ import annotations

from typing import Any

from src.drug_catalog.catalog_service import DrugCatalogService
from src.drug_catalog.db import connect
from src.drug_catalog.models import HospitalDrug

# ── Code system URIs ────────────────────────────────────────────────────────

SYSTEM_RXNORM = "http://www.nlm.nih.gov/research/umls/rxnorm"
SYSTEM_ATC = "http://www.whocc.no/atc"
SYSTEM_SNOMED = "http://snomed.info/sct"
SYSTEM_LOINC = "http://loinc.org"
SYSTEM_ICD10 = "http://hl7.org/fhir/sid/icd-10-cm"
SYSTEM_ACT_CODE = "http://terminology.hl7.org/CodeSystem/v3-ActCode"
SYSTEM_UCUM = "http://unitsofmeasure.org"

# ── LOINC → CpoePatientSnapshot field ─────────────────────────────────────────

LOINC_PATIENT_FIELD: dict[str, str] = {
    "69405-9": "egfr",
    "2160-0": "creatinine",
    "8339-4": "weight_kg",
    "6301-6": "inr",
    "2345-7": "glucose",
    "2823-3": "potassium",
    "1751-7": "albumin",
}

# ── MedSafe alert category → FHIR ActCode ─────────────────────────────────────

ALERT_CATEGORY_TO_ACT_CODE: dict[str, tuple[str, str]] = {
    "drug_interaction": ("DRUGDRUGINT", "Drug-Drug Interaction"),
    "duplicate_ingredient": ("DUPTHRY", "Duplicate Therapy"),
    "allergy": ("ALLERGY", "Allergy"),
    "special_population": ("TREATISSUE", "Treatment Issue"),
    "formulary": ("TREATISSUE", "Treatment Issue"),
    "inventory": ("TREATISSUE", "Treatment Issue"),
    "high_alert": ("TREATISSUE", "Treatment Issue"),
    "terminology": ("TREATISSUE", "Treatment Issue"),
}

INTERACTION_TYPE_CONCEPTS: list[dict[str, str]] = [
    {"code": code, "display": display, "system": SYSTEM_ACT_CODE}
    for code, display in {
        "DRUGDRUGINT": "Drug-Drug Interaction",
        "DUPTHRY": "Duplicate Therapy",
        "ALLERGY": "Allergy",
        "TREATISSUE": "Treatment Issue",
    }.items()
]

# ── CPOE alert level → DetectedIssue.severity ─────────────────────────────────

ALERT_LEVEL_TO_FHIR_SEVERITY: dict[str, str] = {
    "hard_stop": "high",
    "warning": "moderate",
    "info": "low",
}

OVERALL_STATUS_TO_OUTCOME: dict[str, str] = {
    "passed": "information",
    "warning": "warning",
    "blocked": "error",
}


def coding_matches_system(coding: dict[str, Any], system: str) -> bool:
    return (coding.get("system") or "").rstrip("/") == system.rstrip("/")


def extract_coding_code(codeable: dict[str, Any] | None, system: str) -> str:
    if not codeable:
        return ""
    for coding in codeable.get("coding") or []:
        if isinstance(coding, dict) and coding_matches_system(coding, system):
            code = coding.get("code")
            if code:
                return str(code)
    return ""


def extract_coding_display(codeable: dict[str, Any] | None) -> str:
    if not codeable:
        return ""
    if codeable.get("text"):
        return str(codeable["text"])
    for coding in codeable.get("coding") or []:
        if isinstance(coding, dict) and coding.get("display"):
            return str(coding["display"])
    return ""


def act_code_for_category(category: str) -> tuple[str, str]:
    return ALERT_CATEGORY_TO_ACT_CODE.get(
        category.lower().strip(),
        ("TREATISSUE", "Treatment Issue"),
    )


def resolve_drug_by_rxnorm(catalog: DrugCatalogService, rxcui: str) -> HospitalDrug | None:
    if not rxcui:
        return None
    conn = connect(catalog.db_path)
    try:
        row = conn.execute(
            """
            SELECT * FROM hospital_drugs
            WHERE rxnorm_rxcui = ?
            ORDER BY in_formulary DESC, in_stock DESC
            LIMIT 1
            """,
            (rxcui.strip(),),
        ).fetchone()
        if not row:
            return None
        from src.drug_catalog.catalog_service import _row_to_drug

        return _row_to_drug(row)
    finally:
        conn.close()


def resolve_drug_by_atc(catalog: DrugCatalogService, atc_code: str) -> HospitalDrug | None:
    if not atc_code:
        return None
    conn = connect(catalog.db_path)
    try:
        row = conn.execute(
            """
            SELECT * FROM hospital_drugs
            WHERE atc_code = ?
            ORDER BY in_formulary DESC, in_stock DESC
            LIMIT 1
            """,
            (atc_code.strip().upper(),),
        ).fetchone()
        if not row:
            return None
        from src.drug_catalog.catalog_service import _row_to_drug

        return _row_to_drug(row)
    finally:
        conn.close()


def snomed_to_condition_term(codeable: dict[str, Any] | None) -> str:
    display = extract_coding_display(codeable)
    if display:
        return display
    code = extract_coding_code(codeable, SYSTEM_SNOMED)
    return code or ""
