"""Batch warm: VLM analysis + full multi-agent medication review + persisted report."""
from __future__ import annotations

from src.imaging.analysis_cache import ImagingAnalysisCacheStore
from src.imaging.case_persist import persist_imaging_report_case
from src.imaging.report_cache import ImagingReportCacheStore
from src.imaging.warm_analysis import resolve_study_source_images, warm_study_analysis
from src.reports.report_generator import ReportGenerator
from src.schemas import CandidateDrug, ClinicalReport, GenerateReportRequest, ImagingAnalysisCacheEntry, ImagingStudyItem

WARM_CACHE_USER_ID = "imaging_warm_cache"

# When VLM returns no structured recommended_drugs, use modality-appropriate candidates for review.
SOURCE_FALLBACK_CANDIDATES: dict[str, list[CandidateDrug]] = {
    "mimic_cxr": [
        CandidateDrug(name="levofloxacin", dose="750 mg", route="PO", frequency="qd", indication="CAP"),
        CandidateDrug(name="azithromycin", dose="500 mg", route="PO", frequency="qd", indication="CAP"),
    ],
    "chest_ct": [
        CandidateDrug(name="levofloxacin", dose="750 mg", route="IV", frequency="qd", indication="重症肺炎"),
        CandidateDrug(name="methylprednisolone", dose="40 mg", route="IV", frequency="qd", indication="COPD 加重"),
    ],
    "brats2024": [
        CandidateDrug(name="dexamethasone", dose="4 mg", route="PO", frequency="q6h", indication="脑水肿"),
        CandidateDrug(name="levetiracetam", dose="500 mg", route="PO", frequency="bid", indication="癫痫预防"),
    ],
    "kits19": [
        CandidateDrug(name="cefazolin", dose="1 g", route="IV", frequency="q8h", indication="围术期预防"),
    ],
    "mimic": [
        CandidateDrug(name="spironolactone", dose="25 mg", route="PO", frequency="qd", indication="原醛症"),
        CandidateDrug(name="lisinopril", dose="10 mg", route="PO", frequency="qd", indication="高血压"),
    ],
}


def resolve_candidate_drugs(study: ImagingStudyItem, vlm: dict) -> list[CandidateDrug]:
    drugs = ReportGenerator._drugs_from_vlm(vlm)
    if drugs:
        return drugs
    return [d.model_copy() for d in SOURCE_FALLBACK_CANDIDATES.get(study.source, [])]


def build_report_request(
    study: ImagingStudyItem,
    *,
    force_refresh: bool = False,
    candidate_drugs: list[CandidateDrug] | None = None,
) -> GenerateReportRequest:
    image_paths = list(study.image_paths or [])
    if not image_paths:
        image_paths = resolve_study_source_images(study, max_images=4)
    clinical = (study.report_text or f"{study.title} — {study.modality}").strip()
    return GenerateReportRequest(
        patient_id=study.patient_id,
        clinical_text=clinical,
        primary_modality=study.modality,
        modalities=[study.modality],
        imaging_session_label=study.study_id,
        image_paths=image_paths,
        overlay_paths=[],
        screenshot_paths=[],
        models_used=[],
        segmentation_summary="",
        run_medication_review=True,
        use_analysis_cache=True,
        force_refresh=force_refresh,
        candidate_drugs=list(candidate_drugs or []),
    )


def warm_study_full_report(
    study: ImagingStudyItem,
    *,
    clinical_text: str = "",
    force: bool = False,
    user_id: str = WARM_CACHE_USER_ID,
    department: str = "",
) -> tuple[ImagingAnalysisCacheEntry | None, ClinicalReport | None, bool]:
    """
    Run full pipeline: VLM cache → rule review → multi-agent → DeepSeek synthesis → report cache.
    Returns (analysis_entry, clinical_report, from_cache).
    """
    report_cache = ImagingReportCacheStore()
    analysis_cache = ImagingAnalysisCacheStore()

    if not force:
        cached_report = report_cache.get(study.source, study.patient_id, study.study_id)
        if cached_report and cached_report.metadata.get("medication_review_ran"):
            entry = analysis_cache.get(study.source, study.patient_id, study.study_id)
            return entry, cached_report, True

    req = build_report_request(study, force_refresh=force)
    if clinical_text.strip():
        req = req.model_copy(update={"clinical_text": clinical_text.strip()})

    # Ensure VLM analysis exists, then resolve candidate drugs for med review.
    entry = analysis_cache.get(study.source, study.patient_id, study.study_id)
    if force or entry is None:
        entry = warm_study_analysis(study, clinical_text=req.clinical_text, force=force, include_deepseek=False)
    vlm = (entry.vlm_analysis if entry else {}) or {}
    candidates = resolve_candidate_drugs(study, vlm)
    if candidates:
        req = req.model_copy(update={"candidate_drugs": candidates})

    generator = ReportGenerator()
    report = generator.generate(req, user_id=user_id)
    report_cache.save(report, study.source, study.study_id)
    persist_imaging_report_case(
        report,
        req,
        user_id=user_id,
        department=department,
    )
    entry = analysis_cache.get(study.source, study.patient_id, study.study_id)
    return entry, report, False
