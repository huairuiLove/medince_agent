"""Persist imaging report runs to CaseStore (shared by API and batch warm)."""
from __future__ import annotations

from src.case_store import CaseStore
from src.schemas import ClinicalReport, DiagnosisItem, GenerateReportRequest, PatientContext

CASE_STORE = CaseStore()


def vlm_final_recommendation(analysis: dict) -> str:
    for key in ("medication_recommendation", "clinical_analysis", "imaging_findings"):
        text = str(analysis.get(key) or "").strip()
        if text:
            return text
    return str(analysis.get("reasoning") or "").strip() or "影像 VLM 查阅完成"


def patient_context_from_vlm(
    *,
    clinical_text: str,
    analysis: dict,
    department: str,
) -> PatientContext:
    diagnoses = analysis.get("diagnoses") or []
    return PatientContext(
        department=department,
        source_text=clinical_text,
        chief_complaint=str(analysis.get("chief_complaint") or ""),
        symptoms_or_complaints=list(analysis.get("symptoms") or []),
        allergies=list(analysis.get("allergies") or []),
        diagnoses=[DiagnosisItem(name=str(d)) for d in diagnoses],
    )


def persist_imaging_report_case(
    report: ClinicalReport,
    req: GenerateReportRequest,
    *,
    user_id: str,
    department: str = "",
    case_id: str | None = None,
) -> None:
    meta = report.metadata or {}
    vlm = meta.get("vlm_analysis")
    vlm_dict = vlm if isinstance(vlm, dict) else {}
    dept = (department or "").strip()
    patient = req.patient_context
    if patient is None:
        patient = patient_context_from_vlm(
            clinical_text=req.clinical_text,
            analysis=vlm_dict,
            department=dept,
        )
    elif dept and not (patient.department or "").strip():
        patient = patient.model_copy(update={"department": dept})

    agent_opinions = meta.get("agent_opinions") or []
    final = str(meta.get("final_recommendation") or "").strip()
    if not final:
        if agent_opinions and meta.get("arbitration"):
            final = str(meta["arbitration"].get("final_recommendation") or "")
        if not final:
            final = vlm_final_recommendation(vlm_dict)

    patch: dict = {
        "case_kind": "imaging_report",
        "patient_context": patient.model_dump(),
        "candidate_drugs": meta.get("candidate_drugs") or [],
        "vlm_analysis": vlm_dict or None,
        "imaging_report_id": report.report_id,
        "imaging_session_id": report.imaging_session_id,
        "raw_input_text": req.clinical_text,
        "review_output": meta.get("rule_output"),
        "agent_opinions": agent_opinions,
        "debate": meta.get("debate"),
        "safety_panel": meta.get("safety_panel"),
        "arbitration": meta.get("arbitration"),
        "final_recommendation": final,
        "status": "complete",
    }
    CASE_STORE.upsert_case(
        case_id=case_id or req.case_id,
        patch=patch,
        stage="imaging_report",
        payload={"report_id": report.report_id, "modalities": report.modalities},
        user_id=user_id,
        department=dept,
    )
